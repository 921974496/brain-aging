import h5py
import numpy as np
from sklearn.model_selection import train_test_split
from src.baum_vagan.utils import map_image_to_intensity_range


class BatchProvider(object):
    def __init__(self, images, ids, labels):
        self.images = images
        self.labels = labels
        self.ids = ids
        self.np_random = np.random.RandomState(seed=11)
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
            img = np.reshape(img, list(img.shape) + [1])
            yield img, self.labels[iid]

    def next_batch(self, batch_size):
        X_batch = []
        y_batch = []
        for i in range(batch_size):
            x, y = next(self.img_gen)
            X_batch.append(x)
            y_batch.append(y)

        return np.array(X_batch), np.array(y_batch)


class CN_AD_Loader(object):
    def __init__(self, stream_config):
        self.f = h5py.File(stream_config["data_path"])
        self.rescale_to_one = stream_config["rescale_to_one"]

        self.set_up_batches()

    def set_up_batches(self):
        images = self.f["images"][:]
        labels = self.f["labels"][:]

        if self.rescale_to_one:
            for i in range(len(images)):
                images[i] = map_image_to_intensity_range(images[i], -1, 1)

        # Make train-validation-test split
        images_train_and_val, images_test, labels_train_and_val, labels_test = \
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

        self.trainAD = BatchProvider(
            images=images_train,
            ids=train_AD_ids,
            labels=labels_train
        )

        self.trainCN = BatchProvider(
            images=images_train,
            ids=train_CN_ids,
            labels=labels_train
        )

        self.validationAD = BatchProvider(
            images=images_val,
            ids=val_AD_ids,
            labels=labels_val
        )

        self.validationCN = BatchProvider(
            images=images_val,
            ids=val_CN_ids,
            labels=labels_val
        )

        self.testAD = BatchProvider(
            images=images_test,
            ids=test_AD_ids,
            labels=labels_test
        )

        self.testCN = BatchProvider(
            images=images_test,
            ids=test_CN_ids,
            labels=labels_test
        )
