import tensorflow as tf
from importlib import import_module


def parse_hooks(hooks, locals, out_dir):
  training_hooks = []
  for hook in hooks:
    if hook["type"] == "SummarySaverHook":
      name = hook["params"]["name"]
      summary_op = getattr(tf.summary, hook["params"]["op"])
      summary_op = summary_op(name, locals[name])
      hook_class = getattr(tf.train, "SummarySaverHook")
      hook_instance = hook_class(summary_op=summary_op,
                                 out_dir=out_dir,
                                 save_steps=hook["params"]["save_steps"])
    else:
      hook_class = getattr(tf.train, hook["type"])
      hook_instance = hook_class(**hook["params"])
    
    training_hooks.append(hook_instance)

  return training_hooks


class ModelFunction(object):
  """docstring for ModelFunction"""
  def __init__(self, out_dir, hooks):
    super(ModelFunction, self).__init__()
    self.out_dir = out_dir
    self.hooks = hooks
    
  def model_fn(self, features, labels, mode, params, config):
    """Model function for Estimator."""

    first_hidden_layer = tf.layers.dense(features["X"], 10, activation=tf.nn.relu, name="layer0")

    second_hidden_layer = tf.layers.dense(
        first_hidden_layer, 10, activation=tf.nn.relu)

    output_layer = tf.layers.dense(second_hidden_layer, 1)

    predictions = tf.reshape(output_layer, [-1])

    if mode == tf.estimator.ModeKeys.PREDICT:
      return tf.estimator.EstimatorSpec(
          mode=mode,
          predictions={"ages": predictions},
          export_outputs={"ages": tf.estimator.export.PredictOutput({"ages": predictions})})

    loss = tf.losses.mean_squared_error(labels, predictions)

    optimizer = tf.train.GradientDescentOptimizer(
        learning_rate=params["learning_rate"])

    train_op = optimizer.minimize(
        loss=loss, global_step=tf.train.get_global_step())

    #================================================================

    eval_metric_ops = {
        "rmse": tf.metrics.root_mean_squared_error(
            tf.cast(labels, tf.float64), predictions)
    }

    #================================================================
    training_hooks = parse_hooks(self.hooks, locals(), self.out_dir)
    """
    training_hooks = []
    model_ops = locals()
    for hook in self.hooks:
      if hook["type"] == "SummarySaverHook":
        name = hook["params"]["name"]
        summary_op = getattr(import_module(tf.summary), hook["params"]["op"])
        summary_op = summary_op(name, model_ops[name])
        hook_class = getattr(import_module(tf.train), "SummarySaverHook")
        hook_instance = hook_class(summary_op=summary_op,
                                   out_dir=self.out_dir,
                                   save_steps=hook["params"]["save_steps"])
      else:
        hook_class = getattr(import_module(tf.train), hook["type"])
        hook_instance = hook_class(**hook["params"])
      
      training_hooks.append(hook_instance)
    """
    #================================================================


    if mode == tf.estimator.ModeKeys.TRAIN or mode == tf.estimator.ModeKeys.EVAL:
      return tf.estimator.EstimatorSpec(
          mode=mode,
          loss=loss,
          train_op=train_op,
          eval_metric_ops=eval_metric_ops,
          training_hooks=training_hooks)
