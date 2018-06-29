import os
import json
import tensorflow as tf
from tensorflow.python.summary import summary as core_summary
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, recall_score
import pandas as pd
import csv


from src.test_retest import numpy_utils
from src.test_retest.metrics import specificity_score
from src.test_retest.mri.feature_analysis import RobustnessMeasureComputation


class HookFactory(object):
    def __init__(self,
                 streamer,
                 logger,
                 out_dir,
                 model_save_path,
                 epoch):
        self.streamer = streamer
        self.logger = logger
        self.out_dir = out_dir
        self.model_save_path = model_save_path
        self.epoch = epoch

    def get_batch_dump_hook(self, tensor_val, tensor_name):
        train_hook = BatchDumpHook(
            tensor_batch=tensor_val,
            batch_names=tensor_name,
            model_save_path=self.model_save_path,
            out_dir=self.out_dir,
            epoch=self.epoch,
            train=True
        )
        test_hook = BatchDumpHook(
            tensor_batch=tensor_val,
            batch_names=tensor_name,
            model_save_path=self.model_save_path,
            out_dir=self.out_dir,
            epoch=self.epoch,
            train=False
        )
        return train_hook, test_hook

    def get_robustness_analysis_hook(self, feature_folder, train,
                                     streamer_config):
        hook = RobustnessComputationHook(
            model_save_path=self.model_save_path,
            out_dir=self.out_dir,
            epoch=self.epoch,
            train=train,
            feature_folder=feature_folder,
            robustness_streamer_config=streamer_config
        )

        return hook

    def get_logistic_prediction_hook(
            self,
            train_feature_folder,
            test_feature_folder,
            target_label):
        hook = LogisticPredictionHook(
            train_folder=train_feature_folder,
            test_folder=test_feature_folder,
            streamer=self.streamer,
            model_save_path=self.model_save_path,
            out_dir=self.out_dir,
            epoch=self.epoch,
            target_label=target_label,
            logger=self.logger
        )

        return hook

    def get_prediction_robustness_hook(self):
        hook = PredictionRobustnessHook(
                epoch=self.epoch,
                out_dir=self.out_dir,
                model_save_path=self.model_save_path,
                streamer=self.streamer
        )
        return hook


class CollectValuesHook(tf.train.SessionRunHook):
    """
    Collect values and write them to sumatra_outcome.json
    """
    def __init__(self, tensor_dic, metric_logger):
        """
        Args:
            - tensor_dic: dictionary mapping names to tensors
            - metric_logger: src.logging.MetricLogger object
        """
        self.tensor_dic = tensor_dic
        self.metric_logger = metric_logger

    def before_run(self, run_context):
        # All tensors in tensor_dic will be evaluated
        return tf.train.SessionRunArgs(fetches=self.tensor_dic)

    def after_run(self, run_context, run_values):
        # run_values.results contains the values of the evaluated
        # tensors
        self.metric_logger.log_hook_results(run_values.results)

    def end(self, session):
        print("end of session")


class ConfusionMatrixHook(tf.train.SessionRunHook):
    def __init__(self, pred_1, pred_2, n_classes, out_dir):
        self.pred_1 = pred_1
        self.pred_2 = pred_2
        self.n_classes = n_classes
        self.out_dir = out_dir
        self.confusion = np.zeros((n_classes, n_classes))

    def before_run(self, run_context):
        return tf.train.SessionRunArgs(fetches=[self.pred_1, self.pred_2])

    def after_run(self, run_context, run_values):
        pred_1 = run_values.results[0]
        pred_2 = run_values.results[1]

        # Update counts in confusion matrix
        n = len(pred_1)
        for k in range(n):
            i = pred_1[k]
            j = pred_2[k]

            self.confusion[i, j] += 1

    def end(self, session):
        """
        Dump the confusion matrix.
        """
        if not os.path.exists(self.out_dir):
            os.mkdir(self.out_dir)
        # Check how many confusion matrices there are in the folder
        names = os.listdir(self.out_dir)
        count = len(list(filter(lambda x: "confusion" in x, names)))
        out_file = os.path.join(
            self.out_dir,
            "confusion_" + str(count) + ".npy"
        )

        np.save(out_file, self.confusion.astype(int))


class BatchDumpHook(tf.train.SessionRunHook):
    """
    Dump tensor to file.
    """
    def __init__(self, tensor_batch, batch_names, model_save_path,
                 out_dir, epoch, train=True):
        self.tensor_batch = tensor_batch
        self.batch_names = batch_names
        self.epoch = epoch
        # Extract smt label
        label = os.path.split(model_save_path)[-1]
        if train:
            sub = "train" + "_" + str(epoch)
        else:
            sub = "test" + "_" + str(epoch)
        self.out_dir = os.path.join(out_dir, label, sub)
        if not os.path.exists(self.out_dir):
            os.makedirs(self.out_dir)

    def get_feature_folder_path(self):
        return self.out_dir

    def before_run(self, run_context):
        return tf.train.SessionRunArgs(
            fetches=[self.tensor_batch, self.batch_names]
        )

    def after_run(self, run_context, run_values):
        batch, names = run_values.results

        for val, name in zip(batch, names):
            if isinstance(name[0], int):
                s_name = str(name[0])
            else:
                s_name = name[0].decode('utf-8')
            out_file = os.path.join(
                self.out_dir,
                s_name + ".npy"
            )
            with open(out_file, 'wb') as f:
                np.save(f, val)


class RobustnessComputationHook(tf.train.SessionRunHook):
    def __init__(self, model_save_path, out_dir, epoch, train,
                 feature_folder, robustness_streamer_config):
        self.model_save_path = model_save_path
        self.out_dir = out_dir
        self.epoch = epoch
        self.train = train
        self.feature_folder = feature_folder
        self.robustness_streamer_config = robustness_streamer_config        

    def end(self, session):
        if self.train:
            suff = "train_"
        else:
            suff = "test_"

        suff += str(self.epoch)
        # Construct robustness analyzer
        output_dir = self.out_dir
        file_type = ".npy"
        file_name_key = "image_label"
        robustness_folder = "robustness_" + suff
        features_path = self.feature_folder
        self.streamer_collection = {}
        robustness_funcs = [
            "src.test_retest.numpy_utils.ICC_C1",
            "src.test_retest.numpy_utils.ICC_A1",
            "src.test_retest.numpy_utils.pearsonr",
            "src.test_retest.numpy_utils.linccc",
        ]

        rs = self.robustness_streamer_config
        # Fix datasources
        rs["params"]["stream_config"]["data_sources"][0]["glob_pattern"] = \
            self.feature_folder + "/*_*.npy"

        self.analyzer = RobustnessMeasureComputation(
            robustness_funcs=robustness_funcs,
            features_path=features_path,
            file_type=file_type,
            streamer_collection=rs,
            file_name_key=file_name_key,
            output_dir=output_dir,
            robustness_folder=robustness_folder
        )
        self.analyzer.set_save_path(self.model_save_path)
        self.analyzer.transform(None, None)


class LogisticPredictionHook(tf.train.SessionRunHook):
    """
    Makes predictions based on the learnt embeddings for
    a target label of choice. Embeddings for train and
    test set should be stored in to different folders.
    """
    def __init__(self, train_folder, test_folder, streamer,
                 model_save_path, out_dir, epoch, target_label,
                 logger=None):
        """
        Args:
            - train_folder: folder containing train embeddings
            - test_folder: folder containing test embeddings
            - streamer: used to retrieve target labels
            - model_save_path: sumatra folder
            - out_dir: folder containing produced files that should
              not be tracked by sumatra
            - epoch: i-th epoch
            - target_label: label we want to predict
        """
        self.train_folder = train_folder
        self.test_folder = test_folder
        self.model_save_path = model_save_path
        smt_label = os.path.split(model_save_path)[-1]
        self.out_dir = os.path.join(
            out_dir,
            smt_label,
            "predictions_" + str(epoch)
        )
        if not os.path.exists(self.out_dir):
            os.makedirs(self.out_dir)

        self.streamer = streamer
        self.target_label = target_label
        self.logger = logger

    def load_data(self, folder):
        vecs = []
        labels = []
        image_labels = []
        for f in os.listdir(folder):
            p = os.path.join(folder, f)
            x = np.load(p)
            vecs.append(x)
            # Retrieve label
            file_name = f.split("_")[0]
            label = self.streamer.get_meta_info_by_key(
                file_name, self.target_label
            )
            labels.append(int(label))
            image_labels.append(file_name)

        return np.array(vecs), np.array(labels), image_labels

    def dump_predictions(self, image_labels, predictions, pred_id, train):
        """
        Dump predictions to csv file.
        Args:
            - image_labels: images labels used to identify samples in
              raw ADNI csv file.
            - predictions: predicted labels for source images
            - pred_id: string used to identify the dumped csv file
            - train: True iff predictions correspond to training data
        """
        rows = []
        for label, pred in zip(image_labels, predictions):
            rows.append([label, pred])

        if train:
            pred_id += "_train"
        else:
            pred_id += "_test"

        df = pd.DataFrame(
            data=np.array(rows),
            columns=["image_label", "prediction"]
        )
        df.to_csv(
            os.path.join(self.out_dir, pred_id + "_predictions.csv"),
            index=False
        )

    def evaluate(self, est, X_train, y_train, X_test, y_test):
        name = est.__class__.__name__
        est.fit(X_train, y_train)
        balanced = est.get_params()["class_weight"]
        if balanced is None:
            balanced = "not_balanced"
        else:
            balanced = "balanced"

        pred_id = name + "_" + balanced
        preds = est.predict(X_train)
        self.dump_predictions(self.train_image_labels, preds, pred_id, True)

        preds = est.predict(X_test)
        self.dump_predictions(self.test_image_labels, preds, pred_id, False)

        scores = []
        self.funcs = [
            accuracy_score,
            recall_score,
            specificity_score,
            f1_score
        ]

        evals = {}

        # Compute scores
        for f in self.funcs:        
            sc = f(y_test, preds)
            scores.append(round(sc, 4))
            k = pred_id + "_" + f.__name__.split("_")[0]
            evals[k] = sc

        row = [name, balanced] + scores

        # Log scores
        if self.logger is not None:
            self.logger.add_evaluations(
                evaluation_dic=evals,
                namespace="test"
            )
        self.rows.append(row)

    def end(self, session):
        # Make predictions using logistic regression
        # Assumes labels are retrievable by image label
        X_train, y_train, self.train_image_labels = \
            self.load_data(self.train_folder)
        X_test, y_test, self.test_image_labels = \
            self.load_data(self.test_folder)

        ests = [
            LogisticRegression(class_weight='balanced'),
            LogisticRegression()
        ]

        self.rows = []
        for est in ests:
            self.evaluate(est, X_train, y_train, X_test, y_test)

        func_names = [f.__name__.split("_")[0] for f in self.funcs]
        self.df = pd.DataFrame(
            data=np.array(self.rows),
            columns=["Est", "para"] + func_names
        )

        self.df.to_csv(self.out_dir + "/" + "scores.csv", index=False)
        self.df.to_latex(self.out_dir + "/" + "scores.tex", index=False)


class PredictionRobustnessHook(tf.train.SessionRunHook):
    def __init__(self, epoch, out_dir, model_save_path, streamer):
        """
        Analyze robustness of all predictions located
        in prediction folder. There may be multiple files
        of multiple tasks and multiple estimators.
        """
        self.model_save_path = model_save_path
        smt_label = os.path.split(model_save_path)[-1]
        self.input_folder = os.path.join(
            out_dir,
            smt_label,
            "predictions_" + str(epoch)
        )
        self.out_dir = os.path.join(
            out_dir,
            smt_label,
            'prediction_robustness_' + str(epoch)
        )
        if not os.path.exists(self.out_dir):
            os.makedirs(self.out_dir)

        self.streamer = streamer

        # Read test pairs dumped by input streamer
        self.train_pairs = self.read_pairs(train=True)
        self.test_pairs = self.read_pairs(train=False)

    def read_pairs(self, train):
        """"
        Build test-retest pairs.
        """
        file_name = "train_groups.csv"
        if not train:
            file_name = "test_groups.csv"
        p = os.path.join(self.model_save_path, file_name)
        image_labels = []
        with open(p) as csvfile:
            reader = csv.reader(csvfile, delimiter='\t')
            for row in reader:
                for el in row:
                    image_label = os.path.split(el)[-1].split("_")[0]
                    image_labels.append(image_label)

        groups = self.streamer.get_test_retest_pairs(image_labels)

        return [g.file_ids for g in groups]

    def analyze_robustness(self, file_name, predictions):
        funcs = [
            numpy_utils.ICC_C1,
            numpy_utils.ICC_A1,
            numpy_utils.not_equal_pairs,
            numpy_utils.equal_pairs
        ]

        scores = {
            "n_pairs": len(predictions)
        }
        for f in funcs:
            scores[f.__name__] = f(predictions)

        with open(os.path.join(self.out_dir, file_name + ".json"), 'w') as f:
            json.dump(scores, f, indent=2)

    def analyze_file(self, file_path):
        image_label_to_pred = {}
        with open(file_path) as csvfile:
            fname = os.path.split(file_path)[-1].split(".")[0]
            reader = csv.DictReader(csvfile)
            for row in reader:
                k = row["image_label"]
                y = row["prediction"]
                try:
                    y = int(y)
                except ValueError:
                    y = float(y)
                image_label_to_pred[k] = y

            if "train" in fname:
                pairs = self.train_pairs
            elif "test" in fname:
                pairs = self.test_pairs

            predictions = []
            for pa in pairs:
                cur = []
                for el in pa:
                    image_label = self.streamer.get_image_label(el)
                    cur.append(image_label_to_pred[image_label])
                predictions.append(cur)

            self.analyze_robustness(fname, np.array(predictions))

    def end(self, session):
        self.input_paths = []
        for fname in os.listdir(self.input_folder):
            if not fname.endswith("predictions.csv"):
                continue
            p = os.path.join(self.input_folder, fname)
            self.input_paths.append(p)

        for p in self.input_paths:
            self.analyze_file(p)


class ICCHook(tf.train.SessionRunHook):
    def __init__(self, icc_op, out_dir, icc_name):
        self.icc_op = icc_op
        self.out_dir = out_dir
        self.icc_name = icc_name
        self.batch_iccs = []

    def before_run(self, run_context):
        return tf.train.SessionRunArgs(fetches=self.icc_op)

    def after_run(self, run_context, run_values):
        feature_iccs = run_values.results
        self.batch_iccs.append(feature_iccs)

    def end(self, session):
        X = np.array(self.batch_iccs)

        if not os.path.exists(self.out_dir):
            os.mkdir(self.out_dir)
        # Check how many confusion matrices there are in the folder
        names = os.listdir(self.out_dir)
        count = len(list(filter(lambda x: self.icc_name in x, names)))
        out_file = os.path.join(
            self.out_dir,
            self.icc_name + "_" + str(count) + ".npy"
        )

        np.save(out_file, X)


class SumatraLoggingHook(tf.train.SessionRunHook):
    def __init__(self, ops, names, logger, namespace):
        self.ops = ops
        self.names = names
        self.logger = logger
        self.namespace = namespace
        self.name_to_values = {
            name: []
            for name in names
        }

    def before_run(self, run_context):
        return tf.train.SessionRunArgs(fetches=self.ops)

    def after_run(self, run_context, run_values):
        values = run_values.results

        for val, name in zip(values, self.names):
            self.name_to_values[name].append(val)

    def end(self, session):
        # Compute average over batches
        evals = {}
        for name, values in self.name_to_values.items():
            evals[name] = np.mean(values)

        self.logger.add_evaluations(
            namespace=self.namespace,
            evaluation_dic=evals
        )


class PrintAndLogTensorHook(tf.train.LoggingTensorHook):
    def __init__(
        self,
        estimator,
        print_summary_init_value=0.5,
        print_summary_tensor=None,
        **kwargs
    ):
        super(PrintAndLogTensorHook, self).__init__(**kwargs)
        self.estimator = estimator
        self.print_summary_tensor = print_summary_tensor
        self.print_aggregated_history = [print_summary_init_value] * 30

    def _log_tensors(self, tensor_values):
        """
        tensor_values is a dict {string => tensor_value }
        """
        elapsed_secs, _ = self._timer.update_last_triggered_step(self._iter_count)
        self.estimator.training_log_values(tensor_values)
        # super(PrintAndLogTensorHook, self)._log_tensors(tensor_values)
        if self.print_summary_tensor is not None:
            self.print_aggregated_history.append(
                tensor_values[self.print_summary_tensor]
            )
            print(
                'Entrack',
                'Step:', tensor_values['global_step'],
                'Loss:', tensor_values['global_optimizer_loss'],
                self.print_summary_tensor, np.mean(
                    self.print_aggregated_history[-20:-1]
                )
            )


class SessionHookFullTrace(tf.train.SessionRunHook):
    """Hook to perform Traces every N steps."""

    def __init__(
        self,
        ckptdir,
        first_step=True,
        every_step=50,
        trace_level=tf.RunOptions.FULL_TRACE,
    ):
        self.ckptdir = ckptdir
        self.trace_level = trace_level
        self.every_step = every_step
        self.first_step = first_step
        self._trace = False

    def begin(self):
        self._global_step_tensor = tf.train.get_global_step()
        if self._global_step_tensor is None:
            raise RuntimeError("Global step should be created to use SessionHookFullTrace.")

    def before_run(self, run_context):
        if self._trace:
            options = tf.RunOptions(trace_level=self.trace_level)
        else:
            options = None
        return tf.train.SessionRunArgs(fetches=self._global_step_tensor,
                                       options=options)

    def after_run(self, run_context, run_values):
        global_step = run_values.results - 1
        if self._trace:
            self._trace = False
            writer = core_summary.FileWriterCache.get(self.ckptdir)
            writer.add_run_metadata(
                run_values.run_metadata,
                '{global_step}'.format(global_step=global_step),
                global_step,
            )
            writer.flush()
        if (self.every_step is not None and
                not (global_step + 1) % self.every_step):
            self._trace = True
        if self.first_step and global_step == 1:
            self._trace = True


class SessionHookDumpTensors(tf.train.SessionRunHook):
    """ Dumps tensors to file """

    def __init__(self, ckptdir, tensors_dict):
        self.ckptdir = ckptdir
        self.tensors_dict = tensors_dict

    def begin(self):
        self.tensors_dict['global_step'] = tf.train.get_global_step()

    def before_run(self, run_context):
        return tf.train.SessionRunArgs(fetches=self.tensors_dict)

    def after_run(self, run_context, run_values):
        if len(run_values.results) <= 1:
            return
        out_file = os.path.join(self.ckptdir, 'tensors_dump.json')
        try:
            tensors_values = json.load(open(out_file, 'r+'))
        except IOError:
            tensors_values = {}
        step = str(run_values.results['global_step'])
        if step not in tensors_values:
            tensors_values[step] = []
        del run_values.results['global_step']
        tensors_values[step].append({
            name: value.tolist()
            for name, value in run_values.results.items()
        })
        json.dump(tensors_values, open(out_file, 'w+'))
