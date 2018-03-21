import re
import os
import glob
import subprocess
import xml.etree.ElementTree as ET
import json
import pickle
from modules.models.utils import custom_print


def xml_elem_unique(root, path):
    e = root.findall(path)
    assert(len(e) == 1)
    return e[0].text


def filters_match(value, filters):
    match_type = {
        'eq': lambda eq: eq == value,
        'gt': lambda f: float(value) > f,
        'lt': lambda f: float(value) < f,
        'doesnt_contain': lambda l: l not in value,
    }
    return all([
        match_type[type](type_value)
        for type, type_value in filters.items()
    ])


def build_options(params):
    options_list = []
    if 'B' in params and params['B']:
        options_list.append('-B')
    if 'f' in params:
        options_list.append('-f %.2f' % params['f'])
    if 'g' in params:
        options_list.append('-g %.2f' % params['g'])
    return ' '.join(options_list)


class MriPreprocessingPipeline(object):
    """
    This class handles all the MRI preprocessing.
    Given a $path containing a raw folder, it will:
        1. Extract brains in
            '$path/01_brain_extracted/I{image_id}.nii.gz'
        2. Register brains to a template in
            '$path/02_registered/I{image_id}.nii.gz'
    """

    def __init__(
        self,
        path,
        files_glob,
        extract_image_id_regexp,
        regexp_image_id_group,
        regexp_patient_id_group=None,
        set_all_single_class=None,
        filter_xml=None,
        shard=None,
        steps=[],
        split_train_test=None,
    ):
        self.path = path
        self.steps = steps
        self.split_train_test = split_train_test
        self.all_files = sorted(glob.glob(files_glob))
        self.files = self.all_files
        self.extract_image_id_regexp = re.compile(extract_image_id_regexp)
        self.regexp_image_id_group = regexp_image_id_group
        self.regexp_patient_id_group = regexp_patient_id_group
        self.image_id_enabled = None
        self.image_id_to_class = None
        self.set_all_single_class = None
        self.image_id_to_patient_id = {}
        self.image_id_counter = 0
        if filter_xml is not None:
            self.filter_xml(**filter_xml)
        if shard is not None:
            self.shard(**shard)

    def filter_xml(self, files, xml_image_id, filters, xml_class=None, xml_patient_id=None):
        self.image_id_enabled = set()
        self.image_id_to_class = {}
        discarded_count = 0
        for f in glob.glob(files):
            tree = ET.parse(f)
            root = tree.getroot()
            image_id = int(xml_elem_unique(root, xml_image_id))

            pass_all_filters = True
            for filter in filters:
                value = xml_elem_unique(root, filter['key'])
                if not filters_match(value, filter['value']):
                    pass_all_filters = False
                    break
            if not pass_all_filters:
                discarded_count += 1
                continue
            self.image_id_enabled.add(image_id)
            if xml_class is not None:
                self.image_id_to_class[image_id] = xml_elem_unique(
                    root,
                    xml_class,
                )
            if xml_patient_id is not None:
                self.image_id_to_patient_id[image_id] = xml_elem_unique(
                    root,
                    xml_patient_id,
                )

        custom_print('[filter_xml] %s images discarded' % (discarded_count))

    def shard(self, worker_index, num_workers):
        custom_print('SHARDS: Worker %s/%s' % (worker_index+1, num_workers))
        assert(worker_index < num_workers)
        self.files = [
            f
            for i, f in enumerate(self.all_files)
            if (i % num_workers) == worker_index
        ]

    def transform(self, X=None):
        steps_registered = {
            'no_operation': self.no_operation,
            'exec_command': self.exec_command,
            'brain_extraction': self.brain_extraction,
            'template_registration': self.template_registration,
        }
        for step in self.steps:
            self._mkdir(step['subfolder'])
        custom_print('Applying MRI pipeline to %s files' % (len(self.files)))
        all_images_ids = []
        for i, mri_raw in enumerate(self.files):
            image_id, patient_id = self.extract_image_and_patient(mri_raw)
            custom_print('Image %s/%s [image_id = %s]' % (
                i, len(self.files), image_id))
            if self.image_id_enabled is not None:
                if image_id not in self.image_id_enabled:
                    custom_print('... Skipped')
                    continue

            paths = [mri_raw] + [os.path.join(
                    self.path,
                    step['subfolder'],
                    'I{image_id}.nii.gz'.format(image_id=image_id),
                )
                for step in self.steps
            ]
            for step_id, step in enumerate(self.steps):
                if 'skip' in step:
                    continue
                if os.path.exists(paths[step_id+1]) and not step['overwrite']:
                    continue
                steps_registered[step['type']](
                    paths[step_id],
                    paths[step_id+1],
                    image_id,
                    step,
                )
            all_images_ids.append(image_id)

        # Split train/test
        if self.split_train_test is not None:
            self.do_split_train_test(all_images_ids, **self.split_train_test)

    def extract_image_and_patient(self, mri_raw):
        if self.regexp_image_id_group is not None:
            image_id = int(self.extract_image_id_regexp.match(
                mri_raw,
            ).group(self.regexp_image_id_group))
        else:
            image_id = self.image_id_counter
            self.image_id_counter += 1

        if self.regexp_patient_id_group is not None:
            patient_id = int(self.extract_image_id_regexp.match(
                mri_raw,
            ).group(self.regexp_patient_id_group))
            assert(image_id not in self.image_id_to_patient_id)
            self.image_id_to_patient_id[image_id] = patient_id
        else:
            if image_id not in self.image_id_to_patient_id:
                patient_id = None
            else:
                patient_id = self.image_id_to_patient_id[image_id]
        return image_id, patient_id

    # ------------------------- Pipeline main steps
    def no_operation(self, mri_image, mri_output, image_id, params):
        pass

    def exec_command(self, mri_image, mri_output, image_id, params):
        cmd = params['command']
        cmd = cmd.format(
            mri_image=mri_image,
            mri_output=mri_output,
            image_id=image_id,
            **params
        )
        self._exec(cmd)

    def brain_extraction(self, mri_image, mri_output, image_id, params):
        options = params['options']
        if 'images_bet_params' in params:
            bet_options = json.load(open(params['images_bet_params'], 'r'))
            if str(image_id) in bet_options:
                params = bet_options[str(image_id)]
                if params is None:
                    return
                options = build_options(params)

        cmd = 'bet {mri_image} {mri_output} {options}'
        cmd = cmd.format(
            mri_image=mri_image,
            mri_output=mri_output,
            options=options,
        )
        self._exec(cmd)

    def template_registration(self, mri_image, mri_output, image_id, params):
        """
        Registers $mri_image to $mri_template template
        """
        if not os.path.exists(mri_image):
            return

        cmd = 'flirt -in {mri_image} -ref {ref} -out {out} ' + \
            '-cost {cost} -searchcost {searchcost} '
        cmd = cmd.format(
            mri_image=mri_image,
            ref=params['mri_template'],
            out=mri_output,
            cost=params['cost'],
            searchcost=params['searchcost'],
        )
        self._exec(cmd)

    def do_split_train_test(
        self,
        image_ids,
        random_seed,
        pkl_prefix,
        test_images_def,
    ):
        if self.image_id_to_class is None:
            if self.set_all_single_class is None:
                custom_print('Train/Test split: No class loaded from XML.')
                return
            self.image_id_to_class = {
                img_id: self.set_all_single_class
                for img_id in image_ids
            }

        num_images = len(image_ids)
        image_ids = [id for id in image_ids if id in self.image_id_to_class]
        if num_images != len(image_ids):
            custom_print(
                'Train/Test split: %d/%d images with unknown class!' % (
                    num_images - len(image_ids), num_images,
                ))
        # r = random.Random(random_seed)
        all_test = []
        all_train = []
        patients_dict = {}
        for class_idx, class_def in enumerate(test_images_def):
            if not isinstance(class_def['class'], list):
                assert(isinstance(class_def['class'], str))
                class_def['class'] = [class_def['class']]
            # We want to split by patient ID
            # and reach a minimum number of images
            class_images = [
                img_id
                for img_id in image_ids
                if self.image_id_to_class[img_id] in class_def['class']
            ]
            class_images = sorted(
                class_images,
                key=self.image_id_to_patient_id.__getitem__,
            )
            custom_print('Class %d [%s]' % (
                class_idx, ','.join(class_def['class']),
            ))
            num_test_images = class_def['count']
            if num_test_images == 0:
                test_images = []
                train_images = class_images
            else:
                last_test_patient_id = self.image_id_to_patient_id[
                    class_images[num_test_images-1]
                ]
                while self.image_id_to_patient_id[
                    class_images[num_test_images]
                ] == last_test_patient_id:
                    num_test_images += 1
                test_images = class_images[:num_test_images]
                train_images = class_images[num_test_images:]
            custom_print('  TRAIN: %d images / %d patients' % (
                len(train_images), len(set([
                    self.image_id_to_patient_id[img_id]
                    for img_id in train_images
                ])),
            ))
            custom_print('  VALID: %d images / %d patients' % (
                len(test_images), len(set([
                    self.image_id_to_patient_id[img_id]
                    for img_id in test_images
                ])),
            ))
            all_test += test_images
            all_train += train_images
            patients_dict.update({
                'I%d' % id: class_idx
                for id in class_images
            })
        pickle.dump(
            ['I%d' % i for i in all_test],
            open(os.path.join(self.path, '%stest.pkl' % pkl_prefix), 'wb'),
        )
        pickle.dump(
            ['I%d' % i for i in all_train],
            open(os.path.join(self.path, '%strain.pkl' % pkl_prefix), 'wb'),
        )
        pickle.dump(
            patients_dict,
            open(os.path.join(self.path, '%slabels.pkl' % pkl_prefix), 'wb'),
        )

    # ------------------------- Utils and wrappers
    def _exec(self, cmd):
        custom_print('[Exec] ' + cmd)
        os.environ['FSLOUTPUTTYPE'] = 'NIFTI_GZ'
        os.environ['FSLDIR'] = '/local/fsl'
        subprocess.call(cmd, shell=True)

    def _mkdir(self, directory):
        try:
            os.mkdir(os.path.join(self.path, directory))
        except OSError:
            pass
