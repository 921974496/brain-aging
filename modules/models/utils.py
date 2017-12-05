import os
import numpy as np
import tensorflow as tf
import builtins
import nibabel as nib
from modules.models.example_loader import PointExamples
from sklearn.externals import joblib

def convert_nii_and_trk_to_npy(
        nii_file,
        trk_file,
        block_size,
        path,
        n_samples=None):
    """Save the samples to numpy binary format."""
    # The labels are the real vectors.
    label_type = "point"

    example_loader = PointExamples(
        nii_file=nii_file,
        trk_file=trk_file,
        block_size=block_size,
        num_eval_examples=0)

    X = {
        'blocks': [],
        'incoming': [],
        'centers': [],
    }
    y = []

    if n_samples is None:
        n_samples = len(example_loader.train_labels)

    for idx, label in enumerate(example_loader.train_labels):
        if idx >= n_samples:
            break
        block = PointExamples.build_datablock(
            example_loader.brain_data,
            example_loader.block_size,
            label['center'],
            label['incoming'], label['outgoing'],
            label_type)
        X['blocks'].append(block['data_block'])
        X['incoming'].append(block['incoming'])
        X['centers'].append(block['center'])
        y.append(block['outgoing'])


    for key in X.keys():
        X[key] = np.array(X[key])
    y = np.array(y)

    joblib.dump(X, os.path.join(path, "X.pkl"))
    joblib.dump(y, os.path.join(path, "y.pkl"))

def parse_hooks(hooks, locals, outdir):
    training_hooks = []
    for hook in hooks:
        if hook["type"] == "SummarySaverHook":
            name = hook["params"]["name"]
            summary_op = getattr(tf.summary, hook["params"]["op"])
            summary_op = summary_op(name, locals[name])
            hook_class = getattr(tf.train, "SummarySaverHook")
            hook_instance = hook_class(
                summary_op=summary_op,
                output_dir=outdir,
                save_steps=hook["params"]["save_steps"])
        else:
            hook_class = getattr(tf.train, hook["type"])
            hook_instance = hook_class(**hook["params"])

        training_hooks.append(hook_instance)

    return training_hooks


def save_fibers(fiber_list, header, out_name="fibers"):
    """Save fibers form a list.

    Args:
    fiber_list: The list of fibers (lists of lists of points) to be saved.
    header: Original header of the fibers.
    out_name: Name with which to save the '.trk' file.
    """
    streamline = []
    for fiber_idx, _ in enumerate(fiber_list):
        cur_fiber = np.asarray(fiber_list[fiber_idx])
        streamline.append([cur_fiber, None, None])
        # Save new tractography using the header of the predicted fibers
        nib.trackvis.write(out_name + ".trk", streamline, points_space='voxel',
        hdr_mapping=header)


def print(*args, **kwargs):
    builtins.print(*args, flush=True, **kwargs)
