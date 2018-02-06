import tensorflow as tf
import numpy as np
import pickle as pkl
import json
import copy

from modules.models.base import BaseTF as TensorflowBaseEstimator
from modules.models.utils import parse_hooks, custom_print
from preprocessing import preprocess_all_if_needed
from input import input_iterator
from model import Model
from train_hooks import PrintAndLogTensorHook


class Estimator(TensorflowBaseEstimator):
    """docstring for Estimator"""

    def __init__(self, run_config, *args, **kwargs):
        import features
        self.run_config = run_config
        self.sumatra_outcome = {}

        tf_run_config = copy.deepcopy(run_config['tf_estimator_run_config'])
        if 'session_config' in tf_run_config:
            session_config = tf_run_config['session_config']
            gpu_config = session_config.get('gpu_options')
            if gpu_config is not None:
                del session_config['gpu_options']
            session_config_obj = tf.ConfigProto(**session_config)
            if gpu_config is not None:
                for conf_key, conf_val in gpu_config.items():
                    setattr(session_config_obj.gpu_options, conf_key, conf_val)
            tf_run_config['session_config'] = session_config_obj

        super(Estimator, self).__init__(
            config=tf_run_config,
            *args,
            **kwargs
        )
        features.all_features.feature_info[features.MRI]['shape'] = \
            self.input_fn_config['data_generation']['image_shape']
        self.feature_spec = {
            name: tf.placeholder(
                    shape=[None] + ft_info['shape'],
                    dtype=ft_info['type']
                )
            for name, ft_info in features.all_features.feature_info.items()
        }

    def fit_main_training_loop(self, X, y):
        """
        Trains and runs validation regularly at the same time
        """
        self.evaluations = []
        self.training_metrics = []

        def do_evaluate():
            evaluate_fn = self.gen_input_fn(X, y, False, self.input_fn_config)
            assert(evaluate_fn is not None)
            self.evaluations.append(
                    self.estimator.evaluate(input_fn=evaluate_fn)
                )
            self.export_evaluation_stats()

        num_epochs = self.run_config['num_epochs']
        validations_per_epoch = self.run_config['validations_per_epoch']

        # 1st case, evaluation every few epochs
        if validations_per_epoch <= 1:
            validation_counter = 0
            train_fn = self.gen_input_fn(X, y, True, self.input_fn_config)
            for i in range(num_epochs):
                self.estimator.train(input_fn=train_fn)

                # Check if we need to run validation
                validation_counter += validations_per_epoch
                if validation_counter >= 1:
                    validation_counter -= 1
                    do_evaluate()

        # 2nd case, several evaluations per epoch (should be an int then!)
        else:
            iters = num_epochs * validations_per_epoch
            for i in range(iters):
                train_fn = self.gen_input_fn(
                    X, y, True, self.input_fn_config,
                    shard=(i % validations_per_epoch, validations_per_epoch),
                )
                self.estimator.train(input_fn=train_fn)
                do_evaluate()

    def score(self, X, y):
        """
        Only used for prediction apparently. Dont need it now.
        """
        assert(False)

    def model_fn(self, features, labels, mode, params, config):
        """
        https://www.tensorflow.org/extend/estimators#constructing_the_model_fn
        - features: features returned by @gen_input_fn
        - labels: None (not used)
        - mode: {train, evaluate, inference}
        - params: parameters from yaml config file
        - config: tensorflow.python.estimator.run_config.RunConfig
        """

        prediction_info = params['predicted']
        num_classes = len(prediction_info)
        regression = num_classes == 1
        predicted_features = [i['feature'] for i in prediction_info]
        predicted_features_avg = [i['average'] for i in prediction_info]

        m = Model(is_training=(mode == tf.estimator.ModeKeys.TRAIN))
        last_layer = m.gen_last_layer(features)
        if regression:
            predictions = m.gen_head_regressor(
                last_layer,
                predicted_features_avg,
            )
            compute_loss_fn = tf.losses.mean_squared_error
        else:
            predictions = m.gen_head_classifier(
                last_layer,
                num_classes,
            )
            compute_loss_fn = tf.losses.softmax_cross_entropy

        if mode == tf.estimator.ModeKeys.PREDICT:
            return tf.estimator.EstimatorSpec(
                mode=mode,
                predictions={
                    ft_name: predictions[:, i]
                    for i, ft_name in enumerate(predicted_features)
                },
                export_outputs={
                    'outputs': tf.estimator.export.PredictOutput({
                        ft_name: predictions[:, i]
                        for i, ft_name in enumerate(predicted_features)
                    })
                }
            )

        # Compute loss
        labels = [features[ft_name] for ft_name in predicted_features]
        labels = tf.concat(labels, 1)
        batch_size = tf.shape(labels)[0]

        if regression:
            eval_metric_ops = {
                'rmse': tf.metrics.root_mean_squared_error(
                    tf.cast(labels, tf.float32),
                    predictions,
                ),
                'rmse_vs_avg': tf.metrics.root_mean_squared_error(
                    tf.cast(labels, tf.float32),
                    predictions*0.0 + predicted_features_avg,
                ),
            }
        else:
            eval_metric_ops = {
                'accuracy': tf.metrics.accuracy(
                    tf.argmax(predictions, 1),
                    tf.argmax(labels, 1)
                ),
                'false_negatives': tf.metrics.false_negatives(
                    tf.argmax(predictions, 1),
                    tf.argmax(labels, 1)
                ),
                'false_positives': tf.metrics.false_positives(
                    tf.argmax(predictions, 1),
                    tf.argmax(labels, 1)
                ),
            }

        loss = compute_loss_fn(labels, predictions)
        loss_v_avg = compute_loss_fn(
            tf.cast(labels, tf.float32),
            tf.cast(labels, tf.float32)*0.0 + predicted_features_avg,
        )
        accuracy = tf.reduce_mean(tf.cast(
            tf.equal(tf.argmax(predictions, 1), tf.argmax(labels, 1)),
            tf.float32,
        ))

        # Regularization
        reg_weight = None
        if 'regularization_weight' in params:
            reg_weight = params['regularization_weight']
        if reg_weight is None:
            reg_loss_weighted = 0
        else:
            reg_losses = tf.get_collection(tf.GraphKeys.REGULARIZATION_LOSSES)
            reg_loss_weighted = reg_weight * tf.reduce_sum(reg_losses)
        opt_loss = loss + reg_loss_weighted

        # Variables logged during training
        train_log_variables = {
            "optimizer_loss": opt_loss,
            "prediction_loss": loss,
            "loss_v_avg": loss_v_avg,
            "accuracy": accuracy,
        }
        if not regression:
            train_log_variables.update({
                'predicted_%s_ratio' % predicted_features[i]:
                tf.reduce_sum(tf.cast(
                    tf.equal(tf.argmax(predictions, 1), i),
                    tf.float32,
                )) / tf.cast(batch_size, tf.float32)
                for i in range(num_classes)
            })
        if reg_weight is not None:
            train_log_variables.update({
                'regularization_loss_weighted': reg_loss_weighted,
            })

        # Optimizer
        optimizer = tf.train.AdamOptimizer()
        train_op = optimizer.minimize(
            loss=opt_loss,
            global_step=tf.train.get_global_step(),
        )

        return tf.estimator.EstimatorSpec(
            mode=mode,
            loss=opt_loss,
            train_op=train_op,
            eval_metric_ops=eval_metric_ops,
            training_hooks=self.get_training_hooks(
                params,
                log_variables=train_log_variables,
            ),
        )

    def get_training_hooks(self, params, log_variables):
        if "hooks" in params:
            training_hooks = parse_hooks(
                params["hooks"],
                locals(),
                self.save_path)
        else:
            training_hooks = []

        if "train_log_every_n_iter" in params:
            hook_logged = log_variables.copy()
            hook_logged.update({
                "global_step": tf.train.get_global_step(),
            })
            training_hooks.append(
                PrintAndLogTensorHook(
                    self,
                    hook_logged,
                    every_n_iter=params["train_log_every_n_iter"],
                )
            )
        return training_hooks

    def compute_loss(self, labels, predictions):
        return tf.losses.mean_squared_error(labels, predictions)

    def gen_input_fn(self, X, y=None, train=True, input_fn_config={}, shard=None):
        preprocess_all_if_needed(input_fn_config['data_generation'])

        def _input_fn():
            return input_iterator(
                input_fn_config['data_generation'],
                input_fn_config['data_streaming'],
                shard=shard,
                type='train' if train else 'test'
            )
        return _input_fn

    def training_log_values(self, values):
        self.training_metrics.append(values)

    def export_evaluation_stats(self):
        """
        @values is a list of return values of tf.Estimator.evaluate
        """

        if self.evaluations == []:
            return
        validations_per_epoch = self.run_config['validations_per_epoch']
        self.sumatra_outcome['numeric_outcome'] = {}
        output_dir = self.config["model_dir"]
        last_epoch = len(self.evaluations) / float(validations_per_epoch)
        custom_print('[INFO] Exporting metrics to "%s"' % output_dir)
        # List of dicts to dict of lists
        v_eval = dict(zip(
            self.evaluations[0],
            zip(*[d.values() for d in self.evaluations])
        ))
        v_train = dict(zip(
            self.training_metrics[0],
            zip(*[d.values() for d in self.training_metrics])
        ))

        for v, prefix in [[v_eval, ''], [v_train, 'train/']]:
            for label, values in v.items():
                # Need to skip first value, because loss is not evaluated
                # at the beginning
                x_values = np.linspace(
                    0,
                    last_epoch,
                    len(values)+1,
                )

                # All this data needs to be serializable, so get rid of
                # numpy arrays, np.float32 etc..
                self.sumatra_outcome['numeric_outcome'][prefix + label] = {
                    'type': 'numeric',
                    'x': x_values[1:].tolist(),
                    'x_label': 'Training epoch',
                    'y': np.array(values).tolist(),
                }

        if 'accuracy' in v_eval and len(v_eval['accuracy']) >= 8:
            accuracy = v_eval['accuracy']
            last_n = int(len(accuracy)*0.25)
            accuracy = accuracy[len(accuracy)-last_n:]
            self.sumatra_outcome['text_outcome'] = \
                'Final mean accuracy %s (std=%s) on the last %s steps)' % (
                    np.mean(accuracy),
                    np.std(accuracy),
                    last_n,
                )
        else:
            self.sumatra_outcome['text_outcome'] = 'TODO'

        with open('%s/eval_values.pkl' % (output_dir), 'wb') as f:
            pkl.dump({
                'version': 1,
                'validations_per_epoch': validations_per_epoch,
                'evaluate': self.evaluations,
                'train': self.training_metrics,
            }, f, pkl.HIGHEST_PROTOCOL)

        with open('%s/sumatra_outcome.json' % (output_dir), 'w') as outfile:
            json.dump(self.sumatra_outcome, outfile)
