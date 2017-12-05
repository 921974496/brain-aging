import os
import unittest
import modules.models.utils as utils

class TestUtil(unittest.TestCase):

    def test_convert_nii_and_trk_to_npy(self):
        trk_file = "test/iFOD2.trk"
        nii_file = "test/FODl4.nii.gz"
        path = "test"
        utils.convert_nii_and_trk_to_npy(nii_file, trk_file, block_size=3, path=path, n_samples=100)
        self.assertTrue(os.path.exists("test/X.npy"))
        self.assertTrue(os.path.exists("test/y.npy"))
        os.remove("test/X.npy")
        os.remove("test/y.npy")


if __name__ == '__main__':
    unittest.main()
