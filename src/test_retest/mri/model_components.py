import abc
import tensorflow as tf
from src.test_retest import regularizer
from src.test_retest.test_retest_base import \
    linear_trafo_multiple_input_tensors


def name_to_hidden_regularization(layer_id, reg_name, activations_test,
                                  activations_retest):
    if reg_name == regularizer.JS_DIVERGENCE_LABEL:
        s_test = tf.nn.softmax(
            activations_test,
            name=str(layer_id) + "_softmax_test"
        )
        s_retest = tf.nn.softmax(
            activations_retest,
            name=str(layer_id) + "_softmax_retest"
        )
        n = activations_test.get_shape().as_list()[1]
        batch_div = regularizer.batch_divergence(
            s_test,
            s_retest,
            n,
            regularizer.js_divergence
        )
        return tf.reduce_mean(batch_div)

    elif reg_name == regularizer.L2_SQUARED_LABEL:
        return tf.losses.mean_squared_error(
                    activations_test, activations_retest,
                    name=str(layer_id) + "_l2_activations"
               )
    elif reg_name == regularizer.COSINE_SIMILARITY:
        similarities = regularizer.cosine_similarities(
            activations_test,
            activations_retest
        )
        return tf.reduce_mean(similarities)
    else:
        raise ValueError("regularization name '{}' is unknown".format(
                         reg_name))


def normalize_single_image(im):
        mean, var = tf.nn.moments(im, axes=[0])
        std = tf.sqrt(var)
        std += 0.001
        return (im - mean) / std


def normalize_image_batch(batch, voxel_means, voxel_stds):
    # normalize every image
    batch = tf.map_fn(
        normalize_single_image,
        batch
    )

    # voxel normalization computed across train set
    batch = (batch - voxel_means) / voxel_stds

    # normalize every image
    batch = tf.map_fn(
        normalize_single_image,
        batch
    )

    return batch


class Body(abc.ABC):
    def __init__(self, features, params, streamer):
        self.features = features
        self.params = params
        self.streamer = streamer

        self.construct_graph()

    @abc.abstractmethod
    def construct_graph(self):
        pass

    @abc.abstractmethod
    def get_nodes(self):
        pass


class Head(abc.ABC):
    @abc.abstractmethod
    def construct_graph(self):
        pass

    @abc.abstractmethod
    def get_nodes(self):
        pass


class MultiLayerPairEncoder(Body):
    def construct_graph(self):
        features = self.features
        params = self.params

        input_dim = params["input_dim"]
        x_0 = tf.reshape(
            features["X_0"],
            [-1, input_dim]
        )
        x_1 = tf.reshape(
            features["X_1"],
            [-1, input_dim]
        )

        if params["normalize_images"]:
            voxel_means = tf.constant(
                self.streamer.get_voxel_means(),
                dtype=x_0.dtype
            )
            voxel_means = tf.reshape(voxel_means, [-1, input_dim])

            voxel_stds = tf.constant(
                self.streamer.get_voxel_stds(),
                dtype=x_0.dtype
            )
            voxel_stds = tf.reshape(voxel_stds, [-1, input_dim])

            x_0 = normalize_image_batch(x_0, voxel_means, voxel_stds)
            x_1 = normalize_image_batch(x_1, voxel_means, voxel_stds)

        hidden_dim = params["hidden_dim"]
        w = tf.get_variable(
            name="weights",
            shape=[input_dim, hidden_dim],
            dtype=x_0.dtype,
            initializer=tf.contrib.layers.xavier_initializer(seed=43)
        )

        self.x_0 = x_0
        self.x_1 = x_1
        self.enc_0 = tf.matmul(x_0, w, name="hidden_rep_0")
        self.enc_1 = tf.matmul(x_1, w, name="hidden_rep_1")
        self.w = w

    def get_encoding_weights(self):
        return [self.w]

    def get_encodings(self):
        return self.x_0, self.x_1

    def get_nodes(self):
        return self.x_0, self.x_1, self.enc_0, self.enc_1


class MultiLayerPairDecoder(Head):
    def __init__(self, features, params, encoder):
        self.features = features
        self.params = params
        self.encoder = encoder

        self.construct_graph()

    def construct_graph(self):
        params = self.params
        x_0, x_1, enc_0, enc_1 = self.encoder.get_nodes()
        w = self.encoder.get_encoding_weights()[0]

        self.rec_0 = tf.matmul(
            enc_0,
            tf.transpose(w),
            name="reconstruction_0"
        )

        self.rec_1 = tf.matmul(
            enc_1,
            tf.transpose(w),
            name="reconstruction_1"
        )

        # Reconstruction
        loss_0 = tf.losses.mean_squared_error(x_0, self.rec_0)
        loss_1 = tf.losses.mean_squared_error(x_1, self.rec_1)
        self.reconstruction_loss = loss_0 / 2 + loss_1 / 2

        # Regularization
        to_reg_0 = enc_0
        to_reg_1 = enc_1
        diagnose_dim = params["diagnose_dim"]
        hidden_dim = params["hidden_dim"]
        if diagnose_dim > 0:
            patient_dim = hidden_dim - diagnose_dim
            patient_encs_0, diag_encs_0 = tf.split(
                enc_0,
                [patient_dim, diagnose_dim],
                axis=1
            )

            patient_encs_1, diag_encs_1 = tf.split(
                enc_1,
                [patient_dim, diagnose_dim],
                axis=1
            )

            to_reg_0 = diag_encs_0
            to_reg_1 = diag_encs_1

        reg_loss = tf.constant(0, dtype=tf.int32, shape=None)
        reg_lambda = params["hidden_lambda"]
        if reg_lambda != 0:
            reg_name = params["hidden_regularizer"]
            reg_loss = name_to_hidden_regularization(
                0,
                reg_name,
                to_reg_0,
                to_reg_1
            )
            reg_loss *= reg_lambda

        self.reg_loss = tf.cast(reg_loss, self.reconstruction_loss.dtype)
        self.loss = self.reconstruction_loss + self.reg_loss

    def get_reconstruction_loss(self):
        return self.reconstruction_loss

    def get_regularization_loss(self):
        return self.reg_loss

    def get_total_loss(self):
        return self.loss

    def get_nodes(self):
        return self.rec_0, self.rec_1


class PairClassificationHead(Head):
    def __init__(self, features, params, encoder):
        self.features = features
        self.params = params
        self.encoder = encoder

        self.construct_graph()

    def construct_graph(self):
        params = self.params
        features = self.features

        enc_0, enc_1 = self.encoder.get_encodings()
        # Extract labels
        key = params["target_label_key"]
        labels_0 = features[key + "_0"]
        labels_1 = features[key + "_1"]

        # Compute logits
        w, b, out = linear_trafo_multiple_input_tensors(
            Xs=[enc_0, enc_1],
            out_dim=params["n_classes"],
            weight_names=["logit_weight", "logit_bias"],
            output_names=["logits_0", "logits_1"]
        )

        self.logits_0, self.logits_1 = out

        self.probs_0 = tf.nn.softmax(self.logits_0)
        self.probs_1 = tf.nn.softmax(self.logits_1)

        self.preds_0 = tf.argmax(input=self.logits_0, axis=1)
        self.preds_1 = tf.argmax(input=self.logits_1, axis=1)

        self.loss_0 = tf.losses.sparse_softmax_cross_entropy(
            labels=labels_0,
            logits=self.logits_0
        )

        self.loss_1 = tf.losses.sparse_softmax_cross_entropy(
            labels=labels_1,
            logits=self.logits_1
        )

        self.loss_clf = self.loss_0 / 2 + self.loss_1 / 2

        self.acc_0 = tf.reduce_mean(
            tf.cast(tf.equal(self.preds_0, labels_0), tf.int32)
        )

        self.acc_1 = tf.reduce_mean(
            tf.cast(tf.equal(self.preds_1, labels_1), tf.int32)
        )

        # Set some regularizers
        self.loss_o = tf.constant(0, dtype=self.loss_clf.dtype)
        if params["lambda_o"] != 0:
            self.output_regularization()

        self.loss_h = tf.constant(0, dtype=self.loss_clf.dtype)
        if params["hidden_lambda"] != 0:
            self.hidden_regularization()

    def output_regularization(self):
        params = self.params
        lam = params["lambda_o"]
        key = "output_regularizer"

        if params[key] == "kl_divergence":
            loss_o = regularizer.batch_divergence(
                self.probs_0,
                self.probs_1,
                params["n_classes"],
                regularizer.kl_divergence
            )
            loss_o = tf.reduce_mean(loss_o)
        elif params[key] == "js_divergence":
            loss_o = regularizer.batch_divergence(
                self.probs_0,
                self.probs_1,
                params["n_classes"],
                regularizer.js_divergence
            )
            loss_o = tf.reduce_mean(loss_o)
        else:
            raise ValueError("Regularizer not found")

        self.loss_o = lam * loss_o

    def hidden_regularization(self):
        enc_0, enc_1 = self.encoder.get_encodings()
        params = self.params
        reg = name_to_hidden_regularization(
            "last",
            params["hidden_regularizer"],
            enc_0,
            enc_1
        )

        self.loss_h = params["hidden_lambda"] * reg

    def get_losses_with_names(self):
        ops = [self.loss_o, self.loss_h, self.loss_clf]
        names = ["output_loss", "hidden_loss", "cross_entropy"]
        return ops, names

    def get_accuracy(self):
        return self.acc_0 / 2 + self.acc_1 / 2

    def get_total_loss(self):
        return self.loss_clf + self.loss_o + self.loss_h

    def get_predictions(self):
        return self.preds_0, self.preds_1

    def get_nodes(self):
        return self.get_predictions(), self.get_total_loss()
