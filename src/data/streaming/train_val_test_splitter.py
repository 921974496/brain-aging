from sklearn.model_selection import train_test_split
import os
from collections import OrderedDict
import yaml
from sklearn.model_selection import StratifiedKFold
import numpy as np
import warnings

from .mri_streaming import MRISingleStream


class MRIDatasetSplitter(MRISingleStream):
    def __init__(self, stream_config):
        super(MRIDatasetSplitter, self).__init__(
            stream_config=stream_config
        )

    def fit(self, X, y):
        return self

    def set_save_path(self, save_path):
        self.save_path = save_path

    def get_artifical_label(self, patient_id, file_ids):
        pass

    def get_train_ratio(self):
        return self.config["train_ratio"]

    def get_output_folder(self):
        return self.config["split_folder"]

    def dump_train_val_test_split(self, outfolder, train_ids, val_ids, test_ids):
        def dump(fname, fids):
            with open(os.path.join(outfolder, fname), 'w') as f:
                for fid in fids:
                    f.write("{}\n".format(fid))

        if not os.path.exists(outfolder):
            os.makedirs(outfolder)

        dump("train.txt", train_ids)
        dump("validation.txt", val_ids)
        dump("test.txt", test_ids)

    def dump_label_stats(self, outfolder, train_labels, val_labels, test_labels):
        def dump(fname, labels):
            stats = OrderedDict()

            for lab in labels:
                if lab not in stats:
                    stats[lab] = 1
                else:
                    stats[lab] += 1

            with open(os.path.join(outfolder, fname), 'w') as f:
                for k, v in stats.items():
                    f.write("{}: {}\n".format(k, v))

        dump("train_label_stats.txt", train_labels)
        dump("validation_label_stats.txt", val_labels)
        dump("test_label_stats.txt", test_labels)

    def split_checks(self, train_ids, val_ids, test_ids):
        train_set = set(train_ids)
        test_set = set(test_ids)
        val_set = set(val_ids)

        train_patients = set([self.get_patient_id(fid) for fid in train_set])
        val_patients = set([self.get_patient_id(fid) for fid in val_set])
        test_patients = set([self.get_patient_id(fid) for fid in test_set])

        # IDs sets are disjoint
        assert train_set.isdisjoint(val_set)
        assert train_set.isdisjoint(test_set)
        assert test_set.isdisjoint(val_set)

        # patient sets are disjoint
        assert train_patients.isdisjoint(test_patients)
        assert train_patients.isdisjoint(val_patients)
        assert test_patients.isdisjoint(val_patients)

    def one_split(self, file_ids):
        patient_groups = self.make_patient_groups(self.all_file_ids)

        pids = []
        labels = []
        pid_to_fids = {}
        label_counts = {}
        for g in patient_groups:
            fids = g.file_ids
            patient_id = self.get_patient_id(fids[0])
            pid_to_fids[patient_id] = fids
            label = self.get_artifical_label(patient_id, fids)
            if label is not None:
                pids.append(patient_id)
                labels.append(label)
                if label in label_counts:
                    label_counts[label] += 1
                else:
                    label_counts[label] = 1

        for k, v in label_counts.items():
            print("{}: {}".format(k, v))

        # Make train-test split
        assert len(pids) == len(labels)
        train_size = self.get_train_ratio()
        train_val_pids, test_pids, train_val_labels, test_labels = train_test_split(
            pids,
            labels,
            train_size=train_size,
            test_size=1 - train_size,
            random_state=self.seed,
            shuffle=True,
            stratify=labels
        )

        # Make train-val split
        train_pids, val_pids, train_labels, val_labels = train_test_split(
            train_val_pids,
            train_val_labels,
            train_size=train_size,
            test_size=1 - train_size,
            random_state=self.seed,
            shuffle=True,
            stratify=train_val_labels
        )

        train_ids = [fid for pid in train_pids for fid in pid_to_fids[pid]]
        val_ids = [fid for pid in val_pids for fid in pid_to_fids[pid]]
        test_ids = [fid for pid in test_pids for fid in pid_to_fids[pid]]

        self.split_checks(train_ids, val_ids, test_ids)

        # Dump everything to files
        self.dump_train_val_test_split(
            outfolder=self.save_path,
            train_ids=train_ids,
            val_ids=val_ids,
            test_ids=test_ids
        )

        self.dump_label_stats(
            outfolder=self.save_path,
            train_labels=train_labels,
            val_labels=val_labels,
            test_labels=test_labels
        )

        # Dump config
        with open(os.path.join(self.save_path, "config.yaml"), 'w') as f:
            yaml.dump(self.config, f)

    def k_splits(self, file_ids):
        patient_groups = self.make_patient_groups(file_ids)

        pids = []
        labels = []
        pid_to_fids = {}
        label_counts = {}
        for g in patient_groups:
            fids = g.file_ids
            patient_id = self.get_patient_id(fids[0])
            pid_to_fids[patient_id] = fids
            label = self.get_artifical_label(patient_id, fids)
            if label is not None:
                pids.append(patient_id)
                labels.append(label)
                if label in label_counts:
                    label_counts[label] += 1
                else:
                    label_counts[label] = 1

        for k, v in label_counts.items():
            print("{}: {}".format(k, v))

        n_folds = self.config["n_folds"]
        k_fold = StratifiedKFold(
            n_splits=n_folds,
            shuffle=True,
            random_state=self.seed,
        )

        pids = np.array(pids)
        labels = np.array(labels)

        split_id = 0
        for train_val_ind, test_ind in k_fold.split(pids, labels):
            train_val_pids = pids[train_val_ind]
            train_val_labels = labels[train_val_ind]
            test_pids = pids[test_ind]
            test_labels = labels[test_ind]

            # Train-val split
            train_pids, val_pids, train_labels, val_labels = train_test_split(
                train_val_pids,
                train_val_labels,
                train_size=1 - 1 / n_folds,
                test_size=1 / n_folds,
                random_state=self.seed,
                shuffle=True,
                stratify=train_val_labels
            )

            train_ids = [fid for pid in train_pids for fid in pid_to_fids[pid]]
            val_ids = [fid for pid in val_pids for fid in pid_to_fids[pid]]
            test_ids = [fid for pid in test_pids for fid in pid_to_fids[pid]]

            self.split_checks(train_ids, val_ids, test_ids)

            out_dir = os.path.join(self.save_path, "split_{}".format(split_id))
            os.makedirs(out_dir)
            # Dump everything to files
            self.dump_train_val_test_split(
                outfolder=out_dir,
                train_ids=train_ids,
                val_ids=val_ids,
                test_ids=test_ids
            )

            self.dump_label_stats(
                outfolder=out_dir,
                train_labels=train_labels,
                val_labels=val_labels,
                test_labels=test_labels
            )

            # Dump config
            with open(os.path.join(out_dir, "config.yaml"), 'w') as f:
                yaml.dump(self.config, f)

            split_id += 1

    def transform(self, X, y=None):
        fids = self.all_file_ids

        if "use_fold" in self.config:
            fold_name = self.config["use_fold"]
            if fold_name == "train":
                fids = self.get_train_ids()
            elif fold_name == "validation":
                fids = self.get_validation_ids()
            elif fold_name == "test":
                fids = self.get_test_ids()
            else:
                raise ValueError("Invalid fold name")

        if self.config["n_folds"] == 1:
            self.one_split(fids)
        else:
            self.k_splits(fids)


class ConversionSplitter(MRIDatasetSplitter):
    def get_min_max_age_gap(self):
        return self.config["min_max_age_gap"]

    def get_age_ranges(self):
        return self.config["age_ranges"]

    def age_to_range(self, age):
        ranges = self.get_age_ranges()
        for i, r in enumerate(ranges):
            if r[0] <= age <= r[1]:
                return i

        raise ValueError("No range found for given age")

    def get_artifical_label(self, patient_id, file_ids):
        min_max_age_gap = self.get_min_max_age_gap()

        # Sort file IDs by age
        ages = [self.get_exact_age(fid) for fid in file_ids]
        ages = sorted(ages)
        assert all(ages[i] <= ages[i + 1] for i in range(len(ages) - 1))
        max_age_gap = ages[-1] - ages[0]

        if max_age_gap < min_max_age_gap:
            return None

        n_changes = 0
        for i in range(1, len(file_ids)):
            prev_d = self.get_diagnose(file_ids[i - 1])
            cur_d = self.get_diagnose(file_ids[i])

            if cur_d is not prev_d:
                n_changes += 1

        # Check number of conversions
        if n_changes > 1:
            return None

        conv = self.get_diagnose(file_ids[0]) + "/" \
            + self.get_diagnose(file_ids[-1])

        range_id = self.age_to_range(ages[0])
        gender = self.get_gender(file_ids[0])

        return str(range_id) + "_" + str(gender) + "/" + conv


class ClassificationSplitter(MRIDatasetSplitter):
    def get_min_max_age_gap(self):
        return self.config["min_max_age_gap"]

    def get_age_ranges(self):
        return self.config["age_ranges"]

    def age_to_range(self, age):
        ranges = self.get_age_ranges()
        for i, r in enumerate(ranges):
            if r[0] <= age <= r[1]:
                return i

        raise ValueError("No range found for given age")

    def get_artifical_label(self, patient_id, file_ids):
        min_max_age_gap = self.get_min_max_age_gap()

        # Sort file IDs by age
        ages = [self.get_exact_age(fid) for fid in file_ids]
        ages = sorted(ages)
        assert all(ages[i] <= ages[i + 1] for i in range(len(ages) - 1))
        max_age_gap = ages[-1] - ages[0]

        if max_age_gap < min_max_age_gap:
            return None

        n_changes = 0
        for i in range(1, len(file_ids)):
            prev_d = self.get_diagnose(file_ids[i - 1])
            cur_d = self.get_diagnose(file_ids[i])

            if cur_d is not prev_d:
                n_changes += 1

        # Check number of conversions
        if n_changes > 0:
            return None

        conv = self.get_diagnose(file_ids[0]) + "/" \
            + self.get_diagnose(file_ids[-1])

        range_id = self.age_to_range(ages[0])
        gender = self.get_gender(file_ids[0])

        return str(range_id) + "_" + str(gender) + "/" + conv


class MetaInfoSplitter(MRIDatasetSplitter):
    # Split data based on certain allowed values for different
    # properties
    def get_property_values(self):
        return self.config["property_values"]

    def get_age_ranges(self):
        return self.config["age_ranges"]

    def age_to_range(self, age):
        ranges = self.get_age_ranges()
        for i, r in enumerate(ranges):
            if r[0] <= age <= r[1]:
                return i

        raise ValueError("No range found for given age")

    def get_artifical_label(self, patient_id, file_ids):
        property_values = self.get_property_values()
        keys = sorted(list(property_values.keys()))

        label_values = []
        for k in keys:
            allowed = property_values[k]
            actual = self.get_meta_info_by_key(file_ids[0], k)
            if actual not in allowed:
                return None

            label_values.append(str(actual))

        ages = [self.get_exact_age(fid) for fid in file_ids]
        ages = sorted(ages)
        range_id = self.age_to_range(ages[0])
        gender = self.get_gender(file_ids[0])

        label = "_".join(label_values)
        label = str(range_id) + "_" + str(gender) + "_" + label
        return label


class SpecialConversionSplitter(MetaInfoSplitter):
    """
    Put all Delta-(non-)converters into the test split.
    """
    def fit(self, X, y):
        return self

    def transform(self, X, y=None):
        self.split()

    def get_conversion_key(self):
        return self.config["conversion_key"]

    def split(self):
        patient_groups = self.make_patient_groups(self.all_file_ids)
        conv_key = self.get_conversion_key()

        delta_patients = []
        train_patients = []
        train_labels = []
        pid_to_fids = {}
        train_size = self.get_train_ratio()
        stats = OrderedDict()
        # get all Delta-(non-converters)
        for g in patient_groups:
            fids = g.file_ids
            pid = self.get_patient_id(fids[0])
            label = self.get_artifical_label(pid, g.file_ids)

            if label is None:
                continue

            pid_to_fids[pid] = fids
            conv_val = self.get_meta_info_by_key(
                fids[0],
                conv_key
            )

            if conv_val in [0, 1]:
                delta_patients.append(pid)
            else:
                train_patients.append(pid)
                train_labels.append(label)

                if label not in stats:
                    stats[label] = 1
                else:
                    stats[label] += 1

        for k, v in stats.items():
            print("{}: {}".format(k, v))

        dropped = 0
        train_val_patients = []
        train_val_labels = []
        for patient, lab in zip(train_patients, train_labels):
            if stats[lab] < 2:
                dropped += 1
            else:
                train_val_patients.append(patient)
                train_val_labels.append(lab)

        if dropped > 0:
            warnings.warn("dropping {} patients".format(dropped))

        # Train-val split
        train_pids, val_pids, train_labels, val_labels = train_test_split(
            train_val_patients,
            train_val_labels,
            train_size=train_size,
            test_size=1 - train_size,
            random_state=self.seed,
            shuffle=True,
            stratify=train_val_labels
        )

        train_ids = [fid for pid in train_pids for fid in pid_to_fids[pid]]
        val_ids = [fid for pid in val_pids for fid in pid_to_fids[pid]]
        test_ids = [fid for pid in delta_patients for fid in pid_to_fids[pid]]

        self.split_checks(train_ids, val_ids, test_ids)

        # Dump everything to files
        self.dump_train_val_test_split(
            outfolder=self.save_path,
            train_ids=train_ids,
            val_ids=val_ids,
            test_ids=test_ids
        )

        self.dump_label_stats(
            outfolder=self.save_path,
            train_labels=train_labels,
            val_labels=val_labels,
            test_labels=[]
        )

        # Dump config
        with open(os.path.join(self.save_path, "config.yaml"), 'w') as f:
            yaml.dump(self.config, f)


