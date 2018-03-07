"""
!!! WARNING !!!
When using in this script external values (config keys, files, ...)
make sure their content appears somehow in @get_data_preprocessing_values
function. So that when their value change, data is regenerated automatically.
"""

import numpy as np
import tensorflow as tf
import random
import json
import sys
import hashlib
import os
import glob
import datetime
import nibabel as nib
from modules.models.utils import custom_print
import src.features as ft_def
from src.data.features_store import FeaturesStore


class UniqueLogger:
    printed = set()

    @staticmethod
    def log(text):
        if text in UniqueLogger.printed:
            return
        UniqueLogger.printed.add(text)
        custom_print(text)


def get_data_preprocessing_values(config):
    """
    Returns a dictionnary with serializable values.
    Whenever the data should be re-generated, the content
    of the returned dictionnary should change.
    """
    return {
        'sources': [
            json.dumps(s.__dict__) for s in get_all_data_sources(config)
        ],
        'config': config,
        'modules': {
            'tf_major_version': tf.__version__.split('.')[0],
            'extractor_version': 1,
        }
    }


def get_3d_array_dim(a, dim, dim_val):
    assert(dim in [0, 1, 2])
    if dim == 0:
        return a[dim_val, :, :]
    elif dim == 1:
        return a[:, dim_val, :]
    return a[:, :, dim_val]


def iter_slices(img_data, config):
    if 'image_slices' in config:
        for s in config['image_slices']:
            yield get_3d_array_dim(img_data, s['dimension'], s['value'])
    else:
        yield img_data


class DataAggregator:
    def __init__(self, config, converted_dir):
        self.config = config
        self.study_to_id = {}
        compression = getattr(
            tf.python_io.TFRecordCompressionType,
            config['dataset_compression'],
        )
        self.writers = {
            'train': tf.python_io.TFRecordWriter(
                os.path.join(converted_dir, config['train_database_file']),
                tf.python_io.TFRecordOptions(compression),
            ),
            'test': tf.python_io.TFRecordWriter(
                os.path.join(converted_dir, config['test_database_file']),
                tf.python_io.TFRecordOptions(compression),
            ),
        }
        self.value_to_writer = {}
        self.curr_study_id = -1
        self.curr_study_name = ''
        self.count = 0
        self.stats = {}

    def begin_study(self, study_name, total_files):
        self.study_to_id[study_name] = len(self.study_to_id)
        self.curr_study_id = self.study_to_id[study_name]
        self.curr_study_name = study_name
        self.stats[study_name] = {
            'success': 0,
            'errors': []
        }
        self.count = 1
        self.value_to_writer = {}
        self.total_files = total_files

    def get_writer_for_image(self, features):
        ft_value = features[self.config['train_test_split_on_feature']]
        if ft_value not in self.value_to_writer:
            if random.random() < self.config['test_set_size_ratio']:
                self.value_to_writer[ft_value] = self.writers['test']
            else:
                self.value_to_writer[ft_value] = self.writers['train']
        return self.value_to_writer[ft_value]

    def add_image(self, image_path, int64_features):
        Feature = tf.train.Feature
        Int64List = tf.train.Int64List

        if self.count % (self.total_files / 10) == 1:
            UniqueLogger.log('%s: [%s] Processing image #%d/%d...' % (
                str(datetime.datetime.now()), self.curr_study_name,
                self.count, self.total_files))
        self.count += 1

        img_data = nib.load(image_path).get_data()
        if list(img_data.shape) != list(self.config['image_shape']):
            self.add_error(
                image_path,
                'Image has shape %s, expected %s' % (
                    img_data.shape, self.config['image_shape'])
            )
            return

        # Transform features and write
        def _int64_to_feature(v):
            return Feature(int64_list=Int64List(value=[v]))
        int64_features[ft_def.STUDY_ID] = self.curr_study_id
        img_features = {
            k: _int64_to_feature(v)
            for k, v in int64_features.items()
        }

        for s in iter_slices(img_data, self.config):
            self._write_image(
                self.get_writer_for_image(
                    int64_features
                ),
                s,
                img_features,
                image_path,
            )
        self.stats[self.curr_study_name]['success'] += 1

    def _write_image(self, writer, img_data, img_features, image_path):
        img_data = self._norm(
            img_data,
            **self.config['image_normalization']
        )
        img_features[ft_def.MRI] = tf.train.Feature(
            float_list=tf.train.FloatList(
                value=img_data.reshape([-1])
            ),
        )

        # Check we have all features set
        for ft_name in ft_def.all_features.feature_info.keys():
            if ft_name not in img_features:
                UniqueLogger.log('[FATAL] Feature `%s` missing for %s' % (
                    ft_name, image_path))
                assert(False)

        example = tf.train.Example(
            features=tf.train.Features(feature=img_features),
        )
        writer.write(example.SerializeToString())

    def add_error(self, path, message):
        self.stats[self.curr_study_name]['errors'].append(message)

    def finish(self):
        for w in self.writers.values():
            w.close()
        UniqueLogger.log('---- DATA CONVERSION STATS ----')
        for k, v in self.stats.items():
            UniqueLogger.log('%s: %d ok / %d errors' % (
                k, v['success'], len(v['errors'])))
            if len(v['errors']) > 0:
                UniqueLogger.log('    First error:')
                UniqueLogger.log('    %s' % v['errors'][0])

    def _norm(self, mri, enable, outlier_percentile):
        if not enable:
            return mri
        max_value = np.percentile(mri, outlier_percentile)
        mri_for_stats = np.copy(mri)
        mri_for_stats[mri > max_value] = max_value
        m = np.mean(mri_for_stats)
        std = np.std(mri_for_stats)
        return (mri - m) / std


class DataSource(object):
    def __init__(self, config):
        self.config = config
        self.all_files = glob.glob(config['glob'])
        self.features_store = FeaturesStore(
            csv_file_path=config['patients_features'],
            features_from_filename=config['features_from_filename'],
        )

    def preprocess(self, dataset):
        dataset.begin_study(self.config['name'], len(self.all_files))
        random.shuffle(self.all_files)

        # MRI scans
        for f in self.all_files:
            try:
                ft = self.features_store.get_features_for_file(f)
                dataset.add_image(f, ft)
            except LookupError as e:
                dataset.add_error(f, str(e))


def get_all_data_sources(config):
    return [
        DataSource(source_config)
        for source_config in config['data_sources']
    ]


def preprocess_all(config, converted_dir):
    random_state = random.getstate()
    random.seed(config['test_set_random_seed'])
    dataset = DataAggregator(config, converted_dir)
    data_sources = get_all_data_sources(config)
    for e in data_sources:
        e.preprocess(dataset)
    dataset.finish()
    random.setstate(random_state)


def generate_tf_dataset(config):
    """
    Saves data to
    $data_converted_directory/{hash}/...
    And return this directory
    """
    def obj_hash(obj):
        return hashlib.sha1(json.dumps(
            obj,
            ensure_ascii=False,
            sort_keys=True,
        )).hexdigest()[:8]
    current_extractor_values = get_data_preprocessing_values(config)
    h = obj_hash(current_extractor_values)
    converted_dir = os.path.join(config['data_converted_directory'], h)
    extraction_finished_file = os.path.join(converted_dir, "done.json")
    if os.path.isfile(extraction_finished_file):
        UniqueLogger.log(
            '[INFO] Extracted TF Dataset `' + converted_dir +
            '` is up-to-date. Skipping dataset generation :)'
        )
        return converted_dir
    UniqueLogger.log(
        '[INFO] TF Dataset in `' + converted_dir + '` is inexistant. ' +
        'Will generate from scratch.'
    )
    try:
        os.mkdir(converted_dir)
    except OSError:
        UniqueLogger.log(
            '[FATAL] Directory already exists. Maybe another process ' +
            'is currently generating data? If not, rm folder and try again.'
        )
        sys.exit(42)
    json.dump(
        current_extractor_values,
        open(os.path.join(converted_dir, "extractor_values.json"), "wb"),
        ensure_ascii=False,
        sort_keys=True,
        indent=4,
    )

    extract_start = datetime.datetime.now()
    preprocess_all(config, converted_dir)
    extract_end = datetime.datetime.now()
    json.dump({
            'start_time': str(extract_start),
            'end_time': str(extract_end),
            'elapsed': str(extract_end - extract_start),
        },
        open(extraction_finished_file, "wb"),
        ensure_ascii=False,
        sort_keys=True,
        indent=4,
    )
    return converted_dir
