import gzip
import os
import numpy as np
from sklearn.base import TransformerMixin


IMAGE_SIZE = 28


def read_gzip_images(file_path, n_images):
    """
    Assumes data from LeCun.
    Args:
        - file_path: path to gz file containing images
        - n_images: number of images to read

    Return:
        - data: numpy array of size (n_images, image_height, image_width)
          containg images
    """
    with gzip.open(file_path) as bytestream:
        bytestream.read(16)
        buf = bytestream.read(IMAGE_SIZE * IMAGE_SIZE * n_images)
        data = np.frombuffer(buf, dtype=np.uint8).astype(np.float32)
        data = data.reshape(n_images, IMAGE_SIZE, IMAGE_SIZE)

    return data


def read_gzip_labels(file_path, n_images):
    """
    Assumes data from LeCun.
    Args:
        - file_path: path to gz file containing images
        - n_images: number of images to read

    Return:
        - labels: numpy array containing image labels
    """
    with gzip.open(file_path) as bytestream:
        bytestream.read(8)
        buf = bytestream.read(1 * n_images)
        labels = np.frombuffer(buf, dtype=np.uint8).astype(np.int64)

    return labels


def load_training_labels(folder_path):
    """
    Assumes data from LeCun.
    Arg:
        - folder_path: path to folder containing data

    Return:
        - labels: numpy array containing image labels
    """
    labels = read_gzip_labels(
        os.path.join(folder_path, "train-labels-idx1-ubyte.gz"),
        60000
    )

    return labels


def load_test_labels(folder_path):
    """
    Assumes data from LeCun.
    Arg:
        - folder_path: path to folder containing data

    Return:
        - labels: numpy array containing image labels
    """
    labels = read_gzip_labels(
        os.path.join(folder_path, "t10k-labels-idx1-ubyte.gz"),
        60000
    )

    return labels


def load_mnist_training(folder_path):
    """
    Assumes data from LeCun.
    Arg:
        - folder_path: path to folder containing data

    Returns:
        - images: numpy array containing images
        - labels: numpy array containing labels
    """
    # load images
    images = read_gzip_images(
        os.path.join(folder_path, "train-images-idx3-ubyte.gz"),
        60000
    )

    # load labels
    labels = read_gzip_labels(
        os.path.join(folder_path, "train-labels-idx1-ubyte.gz"),
        60000
    )

    return images, labels


def load_mnist_test(folder_path):
    """
    Assumes data from LeCun.
    Arg:
        - folder_path: path to folder containing data

    Returns:
        - images: numpy array containing images
        - labels: numpy array containing labels
    """
    # load images
    images = read_gzip_images(
        os.path.join(folder_path, "t10k-images-idx3-ubyte.gz"),
        10000
    )

    # load labels
    labels = read_gzip_labels(
        os.path.join(folder_path, "t10k-labels-idx1-ubyte.gz"),
        10000
    )

    return images, labels


def load_test_retest(data_path, test_rest_path, n_samples, train):
    """
    Load load pre-sampled test-retest pairs of MNIST digits.
    Args:
        - data_path: path to the MNIST data folder (needed to load
          labels)
        - test_rest_path: path to folder containing test-retest samples
        - n_samples: number of samples to load
        - train: True to load training samples, False to load test
          samples

    Returns:
        - test: array containing test images of test-retest pairs
        - retest: array containg retest images of test-retest pairs
        - labels: array containg labels
    """
    # load labels
    if train:
        labels = load_training_labels(data_path)
    else:
        labels = load_test_labels(data_path)

    with open(test_rest_path, "rb") as f:
        X = np.load(f)

    return X[0, :n_samples, :, :], X[1, :n_samples, :, :], labels[:n_samples]


def load_test_retest_two_labels(data_path, test_rest_path, n_samples, train,
                                mix_pairs=False):
    """
    Load load pre-sampled test-retest pairs of MNIST digits.
    Args:
        - data_path: path to the MNIST data folder (needed to load
          labels)
        - test_rest_path: path to folder containing test-retest samples
        - n_samples: number of samples to load
        - train: True to load training samples, False to load test
          samples
        - uncouple_pairs: True if we pairs should be broken up, i.e.
          test-retest relationship of pairs is broken up

    Returns:
        - test: array containing test images of test-retest pairs
        - retest: array containg retest images of test-retest pairs
        - labels: array containg labels
    """
    # load labels
    if train:
        labels = load_training_labels(data_path)
    else:
        labels = load_test_labels(data_path)

    with open(test_rest_path, "rb") as f:
        X = np.load(f)

    X = X[:, :n_samples, :, :]
    labels = labels[:n_samples]

    test_labels = np.copy(labels)
    retest_labels = np.copy(labels)

    if mix_pairs:
        # shuffle pairs
        n = X.shape[1]
        np.random.seed(40)
        idx = np.arange(n)
        np.random.shuffle(idx)
        X[0, :] = X[0, idx]
        test_labels[:] = test_labels[idx]

        idx = np.arange(n)
        np.random.shuffle(idx)
        X[1, :] = X[1, idx]
        retest_labels[:] = retest_labels[idx]

    return X[0, :n_samples, :, :], X[1, :n_samples, :, :], \
        test_labels[:n_samples], retest_labels[:n_samples]


def _sample_test_retest(n_pairs, images):
    """
    Sample MNIST images using the pixel intensities as a Bernoulli
    distribution.

    Args:
        - n_pairs: number of test-retest image pairs that should be
          sampled
        - images: numpy array containing

    Returns:
        - test: numpy array containing test images
        - retest: numpy array containing retest images
    """
    # sample binary images using intensities as bernoulli images
    test = images
    retest = np.copy(images)

    for i in range(n_pairs):
        maxi = np.max(test[i, :, :])
        for j in range(IMAGE_SIZE):
            for k in range(IMAGE_SIZE):
                p = test[i, j, k] / maxi
                s1, s2 = np.random.binomial(1, p, 2)
                test[i, j, k] = s1
                retest[i, j, k] = s2

    return test, retest


def sample_test_retest_training(folder_path, n_pairs, seed):
    """
    Sample MNIST images using the pixel intensities as a Bernoulli
    distribution.

    Args:
        - folder_path: path to folder containing MNIST data files
        - n_pairs: number of test-retest image pairs that should be
          sampled
        - seed: numpy random seed

    Returns:
        - test: numpy array containing test images
        - retest: numpy array containing retest images
        - labels: numpy array containing images labels
    """
    # Make sampling reproducible
    np.random.seed(seed)

    images, labels = load_mnist_training(folder_path)
    n = len(images)

    # sample source images
    idx = np.random.randint(0, n, min(n_pairs, n))
    images = images[idx]
    labels = labels[idx]

    test, retest = _sample_test_retest(n_pairs, images)

    return test, retest, labels


def sample_test_retest_test(folder_path, n_pairs, seed):
    """
    Sample MNIST images using the pixel intensities as a Bernoulli
    distribution.

    Args:
        - folder_path: path to folder containing MNIST data files
        - n_pairs: number of test-retest image pairs that should be
          sampled
        - seed: numpy random seed

    Returns:
        - test: numpy array containing test images
        - retest: numpy array containing retest images
        - labels: numpy array containing images labels
    """
    # Make sampling reproducible
    np.random.seed(seed)

    images, labels = load_mnist_test(folder_path)
    n = len(images)

    # sample source images
    idx = np.random.randint(0, n, min(n_pairs, n))
    images = images[idx]
    labels = labels[idx]

    test, retest = _sample_test_retest(n_pairs, images)

    return test, retest, labels


class MnistSampler(TransformerMixin):
    """
    Transformer class to sample MNIST images from raw files.
    """
    def __init__(self, np_random_seed, data_path, train_data=True):
        """
        Args:
            - np_random_seed: numpy random seed
            - data_path: path to MNIST data folder
            - train_data: True if training data should be
              sampled, False if test data should be sampled
        """
        self.np_random_seed = np_random_seed
        self.data_path = data_path
        self.train_data = train_data

    def fit(self, X):
        return self

    def transform(self, X, y=None):
        """
        Input is ignored an MNIST data is load from path
        given to the constructor.

        Return:
            - sampled: tuple containing test and retest images
              as numpy arrays in its first and second component
              respectively
        """
        np.random.seed(self.random_seed)
        if self.train_data:
            X, _ = load_mnist_training(self.data_path)
        else:
            X, _ = load_mnist_test(self.data_path)

        n = len(X)
        sampled = _sample_test_retest(n, X)

        return sampled


def find_nearest_neighbour(image_id, images, labels):
    ref_im = images[image_id]
    n = len(images)
    closest = -1
    closest_id = -1
    for i in range(n):
        if i == image_id:
            continue
        if labels[image_id] != labels[i]:
            continue
        diff = np.linalg.norm(ref_im - images[i])
        if (closest == -1) or (closest != -1 and diff < closest):
            closest = diff
            closest_id = i

    return closest_id


class MnistNNTestRetestSampler(TransformerMixin):
    """
    A test-retest pair consists of an MNIST image
    and its nearest neighbourg in the images set
    with the same label. 
    """
    def __init__(self, data_path, n, train_data=True):
        """
        Args:
            - np_random_seed: numpy random seed
            - data_path: path to MNIST data folder
            - train_data: True if training data should be
              sampled, False if test data should be sampled
        """
        self.data_path = data_path
        self.train_data = train_data
        self.n = n

    def fit(self, X, y):
        return self

    def transform(self, X, y=None):
        """
        Input is ignored an MNIST data is load from path
        given to the constructor.

        Return:
            - sampled: tuple containing test and retest images
              as numpy arrays in its first and second component
              respectively
        """
        if self.train_data:
            X, labels = load_mnist_training(self.data_path)
        else:
            X, labels = load_mnist_test(self.data_path)

        n = min(self.n, len(labels))
        test_ids = list(range(n))
        retest_ids = [find_nearest_neighbour(i, X, labels) for i in test_ids]

        retest_images = X[retest_ids, :, :]

        return X[test_ids, :, :], retest_images
