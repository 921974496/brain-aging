import numpy as np
from skimage import filters
import os
import h5py
import yaml


def four_disks(effect_size=50., image_size=100, moving_effect=True,
               big_rad=15, small_rad=9, big=[True, True, True, True],
               center_fixed=True):
    """
    Generates an image with background noise containing 4 disks
    of two differend radii. Arrangment of disks:
    -------------
    |  0  |  1  |
    -------------
    |  2  |  3  |
    -------------

    Args:
        - effect_size: influences the intensity of the generated
          disks
        - image_size: width and height of the output image
        - big_rad: radius in pixels of the large disk
        - small_rad: radius in pixels of the small disk
        - big: list of booleans indicating if the i-th disk
          should be large or small
        - center_fixed: if True the 4 centers correspond to the
          corners of a rectangle

    Returns:
        - img: image with 4 disks without noise
        - img_with_noise: the above image plus noise
    """
    stdbckg = 50.  # std deviation of the background
    stdkernel = 2.5  # std deviation of the Gaussian smoothing kernel
    img = np.zeros([image_size, image_size])

    def draw_disk(center, radius):
        i_pos = range(center[0] - radius - 1, center[0] + radius + 1)
        j_pos = range(center[1] - radius - 1, center[1] + radius + 1)

        for i in i_pos:
            for j in j_pos:
                # check if inside circle
                if (i - center[0]) ** 2 + (j - center[1]) ** 2 <= radius ** 2:
                    img[i, j] = effect_size

    # Compute disk centers
    offset = 10
    if not center_fixed:
        # Large disks
        c1 = (offset + big_rad, offset + big_rad)
        c2 = (offset + big_rad, image_size - offset - big_rad)
        # Small disks
        c3 = (image_size - offset - big_rad, offset + big_rad)
        c4 = (image_size - offset - big_rad, image_size - offset - big_rad)
    else:
        off = int(image_size / 4)
        c1 = (off, off)
        c2 = (off, image_size - off)
        c3 = (image_size - off, off)
        c4 = (image_size - off, image_size - off)

    centers = [c1, c2, c3, c4]
    for b, c in zip(big, centers):
        if b:
            draw_disk(c, big_rad)
        else:
            draw_disk(c, small_rad)

    noise = np.random.normal(
        scale=stdbckg, size=np.asarray([image_size, image_size])
    )
    smnoise = filters.gaussian(noise, stdkernel)
    smnoise = smnoise / np.std(smnoise) * stdbckg
    img_with_noise = img + smnoise

    return img, img_with_noise


def tzero_not_fixed_delta_fixed(
        np_random, image_size, effect_size=100, delta=5,
        big_rads=[10, 12, 15, 17, 20], center_fixed=True):
    """
    Args:
        - np_random: numpy RandomState
        - image_size: width and height of output image
        - effect_size: influences the intensity of the generated
          disks
        - delta: radius difference (in pixels) between the large
          and the small disks
        - big_rads: list of radii from which the large radius is
          sampled
        - center_fixed: if True the 4 centers correspond to the
          corners of a rectangle

    Returns:
        - img_t0: image containing 4 disks with large radius (no noise)
        - img_t1: image containing 4 disks with small radius (no noise)
        - smnoise: image containig only noise
    """
    n = len(big_rads)
    idx = np_random.randint(0, n)
    big_rad = big_rads[idx]
    small_rad = big_rad - delta

    stdbckg = 50.  # std deviation of the background
    stdkernel = 2.5  # std deviation of the Gaussian smoothing kernel
    noise = np_random.normal(
        scale=stdbckg, size=np.asarray([image_size, image_size])
    )
    smnoise = filters.gaussian(noise, stdkernel)
    smnoise = smnoise / np.std(smnoise) * stdbckg

    img_t0, _ = four_disks(
        image_size=image_size,
        effect_size=effect_size,
        small_rad=small_rad,
        big_rad=big_rad,
        big=[True, True, True, True],
        center_fixed=center_fixed
    )

    img_t1, _ = four_disks(
        image_size=image_size,
        effect_size=effect_size,
        small_rad=small_rad,
        big_rad=big_rad,
        big=[False, False, False, False],
        center_fixed=center_fixed
    )

    return img_t0, img_t1, smnoise


def tzero_not_fixed_delta_not_fixed(
        np_random, image_size, effect_size=100,
        deltas=[0, 3, 6, 8], big_rads=[10, 12, 15, 17, 20],
        center_fixed=True):
    """
    Radius difference between large and small disks is sampled as
    well as the large radius. The radius difference is the same
    for the four disks.
    """
    n = len(big_rads)
    idx = np.random.randint(0, n)
    big_rad = big_rads[idx]

    idx = np.random.randint(0, len(deltas))
    delta = deltas[idx]
    small_rad = big_rad - delta

    stdbckg = 50.  # std deviation of the background
    stdkernel = 2.5  # std deviation of the Gaussian smoothing kernel
    noise = np_random.normal(
        scale=stdbckg, size=np.asarray([image_size, image_size])
    )
    smnoise = filters.gaussian(noise, stdkernel)
    smnoise = smnoise / np.std(smnoise) * stdbckg

    img_t0, _ = four_disks(
         effect_size=effect_size,
         small_rad=small_rad,
         image_size=image_size,
         big_rad=big_rad,
         big=[True, True, True, True],
         center_fixed=center_fixed
    )

    img_t1, _ = four_disks(
         effect_size=effect_size,
         image_size=image_size,
         small_rad=small_rad,
         big_rad=big_rad,
         big=[False, False, False, False],
         center_fixed=center_fixed
    )

    return img_t0, img_t1, smnoise, delta


def tzero_fixed_delta_not_fixed(np_random, image_size, effect_size=100,
                                deltas=[5, 10], big_rad=15, center_fixed=True):
    """
    The large radius is fixed, only the radius difference
    between the large and the small disks is sampled.
    """
    stdbckg = 50.  # std deviation of the background
    stdkernel = 2.5  # std deviation of the Gaussian smoothing kernel
    noise = np_random.normal(
        scale=stdbckg, size=np.asarray([image_size, image_size])
    )
    smnoise = filters.gaussian(noise, stdkernel)
    smnoise = smnoise / np.std(smnoise) * stdbckg

    idx = np.random.randint(0, len(deltas))
    delta = deltas[idx]
    small_rad = big_rad - delta

    img_t0, _ = four_disks(
         effect_size=effect_size,
         small_rad=small_rad,
         image_size=image_size,
         big_rad=big_rad,
         big=[True, True, True, True],
         center_fixed=center_fixed
    )

    img_t1, _ = four_disks(
         effect_size=effect_size,
         image_size=image_size,
         small_rad=small_rad,
         big_rad=big_rad,
         big=[False, False, False, False],
         center_fixed=center_fixed
    )

    return img_t0, img_t1, smnoise, delta


"""
The samplers below generate images of different sorts
and save them in hdf5 format. In this format, one dataset
contains the images, one the images without noise and one
the labels.
"""


class Sampler(object):
    def __init__(self, n_images, cn_func, cn_params, ad_func, ad_params,
                 outdir):
        self.n_images = n_images
        self.cn_func = cn_func
        self.ad_func = ad_func
        self.cn_params = cn_params
        self.ad_params = ad_params
        self.outdir = outdir

        if not os.path.exists(outdir):
            os.makedirs(outdir)

    def transform(self, X=None, y=None):
        # sample images
        images = []
        labels = []
        gts = []

        n_cn = self.n_images // 2
        n_ad = self.n_images // 2

        for i in range(n_cn):
            labels.append(0)
            gt, img = self.cn_func(**self.cn_params)
            gts.append(gt)
            images.append(img)

        for i in range(n_ad):
            labels.append(1)
            gt, img = self.ad_func(**self.ad_params)
            gts.append(gt)
            images.append(img)

        images = np.array(images)
        labels = np.array(labels)
        gts = np.array(gts)

        # Save images
        out_path = os.path.join(self.outdir, 'samples.hdf5')
        with h5py.File(out_path, 'w') as f:
            f.create_dataset('images', data=images, dtype=np.float32)
            f.create_dataset('labels', data=labels, dtype=np.uint8)
            f.create_dataset('gts', data=gts, dtype=np.uint8)


class TZeroNotFixedSampler(object):
    def __init__(self, n_images, sample_params,
                 outdir):
        self.n_images = n_images
        self.sample_params = sample_params
        self.outdir = outdir
        self.sample_params["np_random"] = np.random.RandomState(seed=40)

        if not os.path.exists(outdir):
            os.makedirs(outdir)

    def transform(self, X=None, y=None):
        # sample images
        images = []
        labels = []
        gts = []

        n_cn = self.n_images // 2
        n_ad = self.n_images // 2

        for i in range(n_cn):
            labels.append(0)
            gt_t0, gt_t1, noise = tzero_not_fixed_delta_fixed(
                **self.sample_params
            )
            delta_im = gt_t1 - gt_t0
            gts.append(gt_t0)
            images.append(np.stack((gt_t0 + noise, delta_im), axis=-1))

        for i in range(n_ad):
            labels.append(1)
            gt_t0, gt_t1, noise = tzero_not_fixed_delta_fixed(
                **self.sample_params
            )
            delta_im = gt_t1 - gt_t0
            gts.append(gt_t0)
            images.append(np.stack((gt_t0 + noise, delta_im), axis=-1))

        images = np.array(images)
        labels = np.array(labels)
        gts = np.array(gts)

        # Save images
        out_path = os.path.join(self.outdir, 'samples.hdf5')
        with h5py.File(out_path, 'w') as f:
            f.create_dataset('images', data=images, dtype=np.float32)
            f.create_dataset('labels', data=labels, dtype=np.uint8)
            f.create_dataset('gts', data=gts, dtype=np.uint8)


class TZeroNotFixedDeltaNotFixedSampler(object):
    def __init__(self, n_images, sample_params,
                 outdir):
        self.n_images = n_images
        self.sample_params = sample_params
        self.outdir = outdir
        self.sample_params["np_random"] = np.random.RandomState(seed=40)

        if not os.path.exists(outdir):
            os.makedirs(outdir)

    def transform(self, X=None, y=None):
        # sample images
        images = []
        labels = []
        gts = []

        n_cn = self.n_images // 2
        n_ad = self.n_images // 2

        for i in range(n_cn):
            labels.append(0)
            gt_t0, gt_t1, noise, delta = tzero_not_fixed_delta_not_fixed(
                **self.sample_params
            )
            shape = gt_t0.shape
            delta_img = delta * np.ones(shape)
            delta_im = gt_t1 - gt_t0
            gts.append(gt_t0)
            images.append(
                np.stack((gt_t0 + noise, delta_img, delta_im), axis=-1)
            )

        for i in range(n_ad):
            labels.append(1)
            gt_t0, gt_t1, noise, delta = tzero_not_fixed_delta_not_fixed(
                **self.sample_params
            )
            shape = gt_t0.shape
            delta_img = delta * np.ones(shape)
            delta_im = gt_t1 - gt_t0
            gts.append(gt_t0)
            images.append(
                np.stack((gt_t0 + noise, delta_img, delta_im), axis=-1)
            )

        images = np.array(images)
        labels = np.array(labels)
        gts = np.array(gts)

        # Save images
        out_path = os.path.join(self.outdir, 'samples.hdf5')
        with h5py.File(out_path, 'w') as f:
            f.create_dataset('images', data=images, dtype=np.float32)
            f.create_dataset('labels', data=labels, dtype=np.uint8)
            f.create_dataset('gts', data=gts, dtype=np.uint8)

        out_path = os.path.join(self.outdir, 'config.yaml')
        with open(out_path, 'w') as f:
            yaml.dump(self.sample_params, f)


class TZeroFixedDeltaNotFixedSampler(object):
    def __init__(self, n_images, sample_params,
                 outdir):
        self.n_images = n_images
        self.sample_params = sample_params
        self.outdir = outdir
        self.sample_params["np_random"] = np.random.RandomState(seed=40)

        if not os.path.exists(outdir):
            os.makedirs(outdir)

    def transform(self, X=None, y=None):
        # sample images
        images = []
        labels = []
        gts = []

        n_cn = self.n_images // 2
        n_ad = self.n_images // 2

        for i in range(n_cn):
            labels.append(0)
            gt_t0, gt_t1, noise, delta = tzero_fixed_delta_not_fixed(
                **self.sample_params
            )
            shape = gt_t0.shape
            delta_img = delta * np.ones(shape)
            delta_im = gt_t1 - gt_t0
            gts.append(gt_t0)
            images.append(
                np.stack((gt_t0 + noise, delta_img, delta_im), axis=-1)
            )

        for i in range(n_ad):
            labels.append(1)
            gt_t0, gt_t1, noise, delta = tzero_fixed_delta_not_fixed(
                **self.sample_params
            )
            shape = gt_t0.shape
            delta_img = delta * np.ones(shape)
            delta_im = gt_t1 - gt_t0
            gts.append(gt_t0)
            images.append(
                np.stack((gt_t0 + noise, delta_img, delta_im), axis=-1)
            )

        images = np.array(images)
        labels = np.array(labels)
        gts = np.array(gts)

        # Save images
        out_path = os.path.join(self.outdir, 'samples.hdf5')
        with h5py.File(out_path, 'w') as f:
            f.create_dataset('images', data=images, dtype=np.float32)
            f.create_dataset('labels', data=labels, dtype=np.uint8)
            f.create_dataset('gts', data=gts, dtype=np.uint8)

        out_path = os.path.join(self.outdir, 'config.yaml')
        with open(out_path, 'w') as f:
            yaml.dump(self.sample_params, f)
