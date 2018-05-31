import os
import json
import tensorflow as tf
from tensorflow.python.summary import summary as core_summary
import numpy as np


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
        out_file = os.path.join(self.out_dir, "confusion_" + str(count) + ".npy")

        np.save(out_file, self.confusion.astype(int))


class TensorsDumpHook(tf.train.SessionRunHook):
    def __init__(self, tensor_list, out_dir):
        self.tensor_list = tensor_list
        self.out_dir = out_dir

    def before_run(self, run_context):
        return tf.train.SessionRunArgs(fetches=self.tensor_list)

    def after_run(self, run_context, run_values):
        print(">>>>>>>>>>>>> After run")
        for val in run_values.results:
            if not os.path.exists(self.out_dir):
                os.mkdir(self.out_dir)
            print(val)


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
        out_file = os.path.join(self.out_dir, self.icc_name + "_" + str(count) + ".npy")

        np.save(out_file, X)


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
