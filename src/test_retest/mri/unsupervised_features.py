from radiomics import featureextractor
import SimpleITK as sitk
import os
import numpy as np
import json
from memory_profiler import profile
import gc
import tensorflow as tf

from modules.models.data_transform import DataTransformer
from src.test_retest.test_retest_base import EvaluateEpochsBaseTF
from src.test_retest.test_retest_base import linear_trafo
from src.test_retest.test_retest_base import regularizer


class PyRadiomicsFeatures(DataTransformer):
    def __init__(self, streamer):
        # Initialize streamer
        _class = streamer["class"]
        self.streamer = _class(**streamer["params"])

    def get_extractor(self):
        # Initialize extractor
        extractor = featureextractor.RadiomicsFeaturesExtractor()
        extractor.enableAllImageTypes()
        extractor.enableAllFeatures()

        return extractor

    def transform(self, X, y=None):
        out_path = os.path.join(self.save_path, "features")
        os.mkdir(out_path)
        # Stream image one by one
        batches = self.streamer.get_batches()
        for batch in batches:
            for group in batch:
                for file_id in group.get_file_ids():
                    path = self.streamer.get_file_path(file_id)

                    sitk_im = sitk.ReadImage(path)
                    all_ones = np.ones(sitk_im.GetSize())
                    sitk_mask = sitk.GetImageFromArray(all_ones)

                    extractor = self.get_extractor()
                    features = extractor.computeFeatures(sitk_im, sitk_mask, "brain")

                    with open(
                        os.path.join(out_path, str(file_id) + ".json"),
                        "w"
                    ) as f:
                        json.dump(features, f, indent=2)


class PCAAutoEncoder(EvaluateEpochsBaseTF):
    def model_fn(self, features, labels, mode, params):
        input_dim = params["input_dim"]
        input_mri = tf.reshape(
            features["mri"],
            [-1, input_dim]
        )

        hidden_dim = params["hidden_dim"]
        w = tf.get_variable(
            name="weights",
            shape=[input_dim, hidden_dim],
            dtype=input_mri.dtype,
            initializer=tf.contrib.layers.xavier_initializer(seed=43)
        )

        hidden = tf.matmul(input_mri, w, name="hidden_rep")

        reconstruction = tf.matmul(
            hidden,
            tf.transpose(w),
            name="reconstruction"
        )

        predictions = {
            "hidden_rep": hidden,
            "reconstruction": reconstruction
        }

        if mode == tf.estimator.ModeKeys.PREDICT:
            return tf.estimator.EstimatorSpec(
                mode=mode,
                predictions=predictions
            )

        # Compute loss
        loss = tf.reduce_sum(tf.square(input_mri - reconstruction))

        optimizer = tf.train.AdamOptimizer(
            learning_rate=params["learning_rate"]
        )
        train_op = optimizer.minimize(loss, tf.train.get_global_step())

        if mode == tf.estimator.ModeKeys.TRAIN:
            return tf.estimator.EstimatorSpec(
                mode=mode,
                loss=loss,
                train_op=train_op
            )

        return tf.estimator.EstimatorSpec(
            mode=mode,
            loss=loss
        )

    def gen_input_fn(self, X, y=None, train=True, input_fn_config={}):
        return self.streamer.get_input_fn(train)
