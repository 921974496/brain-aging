"""
Load previously generated synthetic data and
stream it in batches
"""
import h5py
import numpy as np
from sklearn.model_selection import train_test_split
import tensorflow as tf
from sklearn.utils import shuffle
import pydoc
import itertools

from src.baum_vagan.utils import map_image_to_intensity_range


def prepare_x_t0_delta_x_t0(images):
    x_0 = images[:, :, :, 0]
    x_1 = images[:, :, :, 0] + images[:, :, :, 1]

    return x_0, x_1


class BatchProvider(object):
    """
    Generator providing batches of images
    and labels.
    """
    def __init__(self, images, ids, labels, image_shape,
                 add_delta_noise=0):
        """
        Args:
            - images: an iterable of all images
            - ids: an iterable of indices, only images
              corresponding to these indices are used
            - labels: iterable of the images' labels
            - image_shape: expected output images shape
            - add_delta_noise: if different from 0, some
              noise is add to delta representing the time
              interval of the t0 and t1 image in a sample
        """
        self.images = images
        self.labels = labels
        self.ids = ids
        assert len(ids) > 0
        self.image_shape = image_shape
        self.np_random = np.random.RandomState(seed=11)
        self.add_delta_noise = add_delta_noise
        self.fid_gen = self.next_fid()
        self.img_gen = self.next_image()

    def next_fid(self):
        self.np_random.shuffle(self.ids)
        p = 0
        while (1):
            if p < len(self.ids):
                yield self.ids[p]
                p += 1
            else:
                p = 0
                self.np_random.shuffle(self.ids)

    def next_image(self):
        while (1):
            iid = next(self.fid_gen)
            img = self.images[iid]
            if list(img.shape) != list(self.image_shape):
                img = np.reshape(img, self.image_shape)

            if self.add_delta_noise > 0:
                noise = self.np_random.normal(
                    loc=0.0,
                    scale=self.add_delta_noise
                )
                img[:, :, 1] += noise

            yield img, self.labels[iid]

    def next_batch(self, batch_size):
        X_batch = []
        y_batch = []
        for i in range(batch_size):
            x, y = next(self.img_gen)
            X_batch.append(x)
            y_batch.append(y)

        X_batch = np.array(X_batch)
        y_batch = np.array(y_batch)

        return X_batch, y_batch


class SameDeltaBatchProvider(object):
    def __init__(self, images, ids, labels, image_shape,
                 add_delta_noise=0):
        """
        Same as BatchProvider, but makes sure that all
        samples with the same batch have the same delta.
        Batches of different deltas are streamed in round
        robin fashion.
        """
        self.images = images
        self.labels = labels
        self.ids = ids
        assert len(ids) > 0
        self.image_shape = image_shape
        self.np_random = np.random.RandomState(seed=11)
        self.add_delta_noise = add_delta_noise

        # map deltas to IDs
        self.match_delta_to_ids()

        # one provider for each delta
        self.delta_to_provider = {}
        for delta in self.deltas:
            self.delta_to_provider[delta] = BatchProvider(
                images=images,
                ids=self.delta_to_ids[delta],
                labels=labels,
                image_shape=image_shape,
                add_delta_noise=add_delta_noise
            )

    def match_delta_to_ids(self):
        self.delta_to_ids = {}
        for iid in self.ids:
            # Extract delta
            img = self.images[iid]
            delta = img[0, 0, 1]
            if delta not in self.delta_to_ids:
                self.delta_to_ids[delta] = [iid]
            else:
                self.delta_to_ids[delta].append(iid)

        self.deltas = sorted(self.delta_to_ids.keys())
        self.delta_gen = itertools.cycle(self.deltas)

    def next_batch(self, batch_size):
        delta = next(self.delta_gen)
        provider = self.delta_to_provider[delta]

        X_batch, y_batch = provider.next_batch(batch_size)
        return X_batch, y_batch


class CN_AD_Loader(object):
    def __init__(self, stream_config):
        # Input file
        self.f = h5py.File(stream_config["data_path"], 'r')
        # Rescale image intensities to [-1, 1] interval
        self.rescale_to_one = stream_config["rescale_to_one"]
        # Image shape expected by the model
        self.image_shape = stream_config["image_shape"]
        self.config = stream_config

        # Can be use to build tf datasets
        if "prepare_images" in self.config:
            self.config["prepare_images"] = pydoc.locate(
                self.config["prepare_images"]
            )

        self.set_up_batches()

    def dump_split(self, path):
        # Compatibility with MRI streamers.
        pass

    def dump_normalization(self, path):
        # Compatibility with MRI streamers.
        pass

    def dump_train_val_test_split(self, path):
        # Compatibility with MRI streamers.
        pass

    def add_delta_noise(self):
        if "delta_noise" in self.config:
            return self.config["delta_noise"]
        else:
            return 0

    def divide_delta(self):
        if "divide_delta" in self.config:
            return self.config["divide_delta"]
        else:
            return 1

    def set_up_batches(self):
        images = self.f["images"][:]
        labels = self.f["labels"][:]

        def normalize_to_range(a, b, mini, maxi, x):
            return a + (x - mini) / (maxi - mini) * (b - a)

        # normalize delta to [10, 100] scale
        if "normalize_delta" in self.config:
            channel = self.config["normalize_delta"]
            mini = np.inf
            maxi = -1000000
            for i in range(len(images)):
                mini = min(np.min(images[i, :, :, channel]), mini)
                maxi = max(np.min(images[i, :, :, channel]), maxi)

            for i in range(len(images)):
                images[i, :, :, channel] = normalize_to_range(
                    10, 100, mini, maxi, images[i, :, :, channel]
                )

            def normalize_delta(x):
                return normalize_to_range(10, 100, mini, maxi, x)
            self.normalize_delta = normalize_delta

        # rescale image intensities to [-1, 1]
        if self.rescale_to_one:
            for i in range(len(images)):
                # only map the first channel
                sample = images[i]
                t0_idx = self.config["x_t0_idx"]
                delta_t0_idx = self.config["delta_x_t0_idx"]
                # compute delta_x_t0 by computing the difference AFTER
                # rescaling x_t0 and x_t1
                x_t0 = sample[:, :, t0_idx:t0_idx + 1]
                delta_x_t0 = sample[:, :, delta_t0_idx:delta_t0_idx + 1]
                x_t1 = x_t0 + delta_x_t0
                resc = map_image_to_intensity_range(
                    np.concatenate((x_t0, x_t1), axis=-1), -1, 1
                )
                x_t0 = resc[:, :, 0]
                delta_x_t0 = resc[:, :, 1] - resc[:, :, 0]
                sample[:, :, t0_idx] = x_t0
                sample[:, :, delta_t0_idx] = delta_x_t0

        # divide every delta by a constant
        if self.divide_delta() > 1:
            d = self.divide_delta()
            delta_idx = self.config["delta_idx"]
            for i in range(len(images)):
                images[i, :, :, delta_idx] /= d

        # Make train-validation-test split
        images_train_and_val, images_test, labels_train_and_val, labels_test =\
            train_test_split(
                images,
                labels,
                test_size=0.2,
                stratify=labels,
                random_state=42
            )

        images_train, images_val, labels_train, labels_val = \
            train_test_split(
                images_train_and_val,
                labels_train_and_val,
                test_size=0.2,
                stratify=labels_train_and_val,
                random_state=42
            )

        n_train = images_train.shape[0]
        n_val = images_val.shape[0]
        n_test = images_test.shape[0]

        train_ids = np.arange(n_train)
        train_AD_ids = train_ids[np.where(labels_train == 1)]
        train_CN_ids = train_ids[np.where(labels_train == 0)]

        test_ids = np.arange(n_test)
        test_AD_ids = test_ids[np.where(labels_test == 1)]
        test_CN_ids = test_ids[np.where(labels_test == 0)]

        val_ids = np.arange(n_val)
        val_AD_ids = val_ids[np.where(labels_val == 1)]
        val_CN_ids = val_ids[np.where(labels_val == 0)]

        Provider = pydoc.locate(self.config["batch_provider"])

        self.trainAD = Provider(
            images=images_train,
            ids=train_AD_ids,
            labels=labels_train,
            image_shape=self.image_shape,
            add_delta_noise=self.add_delta_noise()
        )

        self.trainCN = Provider(
            images=images_train,
            ids=train_CN_ids,
            labels=labels_train,
            image_shape=self.image_shape,
            add_delta_noise=self.add_delta_noise()
        )

        self.validationAD = Provider(
            images=images_val,
            ids=val_AD_ids,
            labels=labels_val,
            image_shape=self.image_shape
        )

        self.validationCN = Provider(
            images=images_val,
            ids=val_CN_ids,
            labels=labels_val,
            image_shape=self.image_shape
        )

        self.testAD = Provider(
            images=images_test,
            ids=test_AD_ids,
            labels=labels_test,
            image_shape=self.image_shape
        )

        self.testCN = Provider(
            images=images_test,
            ids=test_CN_ids,
            labels=labels_test,
            image_shape=self.image_shape
        )

        self.random_state = 0

        # only used for non-GAN settings
        def gen_input_fn(images):
            x_0, x_1 = self.config["prepare_images"](images)
            self.random_state += 1
            x_0, x_1 = shuffle(
                x_0,
                x_1,
                random_state=self.random_state
            )

            return tf.estimator.inputs.numpy_input_fn(
                x={
                    "X_0": x_0,
                    "X_1": x_1,
                },
                shuffle=False,
                batch_size=self.config["batch_size"]
            )

        if "prepare_images" in self.config:
            # tf compatible streamers
            self.train_fn = gen_input_fn(images_train)
            self.validation_fn = gen_input_fn(images_val)
            self.test_fn = gen_input_fn(images_test)

    def get_input_fn(self, mode):
        # only used for non-GAN settings
        if mode == "train":
            return self.train_fn
        elif mode == "validation":
            return self.validation_fn
        elif mode == "test":
            return self.test_fn
        else:
            raise ValueError("Invalid mode {}".format(mode))
