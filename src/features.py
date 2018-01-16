import tensorflow as tf
import config


class FeaturesMgr:
    def __init__(self):
        self.feature_info = {}

    def add(self, s, t=tf.int64, shape=[]):
        self.feature_info[s] = {
            'type': t,
            'shape': shape,
        }
        return s


all_features = FeaturesMgr()

# List features here
AGE = all_features.add('age')
MRI = all_features.add('mri', shape=config.image_shape)
SEX = all_features.add('sex')
STUDY_ID = all_features.add('study_id')
STUDY_IMAGE_ID = all_features.add('study_image_id')
STUDY_PATIENT_ID = all_features.add('study_patient_id')
