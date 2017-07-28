import numpy as np
import sklearn as skl
import pickle
from sklearn.utils import check_random_state
from sklearn.utils.validation import check_array
from sklearn.utils.random import sample_without_replacement
from numpy.testing import assert_equal
import requests

class RandomSelection(skl.base.BaseEstimator, skl.base.TransformerMixin):

    def __init__(self, n_components=1000, random_state=None):
        self.n_components = n_components
        self.random_state = random_state

        self.components = None

    def fit(self, X, y=None):
        X = check_array(X)
        n_samples, n_features = X.shape

        if self.n_components <= 0:
            raise ValueError("n_components must be greater than 0, got %s"
                                         % self.n_components)
        elif self.n_components > n_features:
            warnings.warn("The number of components is higher than the number of"
                          " features: n_features < n_components (%s < %s)."
                          "Setting n_components = n_features."
                          "The dimensionality of the problem will not be reduced."
                          % (n_features, self.n_components),
                          DataDimensionalityWarning)
            self.n_components = n_features

        random_state = check_random_state(self.random_state)
        self.components = sample_without_replacement(
                            n_features,
                            self.n_components,
                            random_state=random_state)

        assert_equal(
            self.components.shape,
            (self.n_components,),
            err_msg=("An error has occurred: The self.components vector does "
                     " not have the proper shape."))

        return self

    def transform(self, X, y=None):
        X = check_array(X)
        n_samples, n_features = X.shape

        if self.components is None:
            raise NotFittedError("No random selection has been fit.")

        if n_features < self.components.shape[0]:
            raise ValueError("Impossible to perform selection:"
                "X has less features than should be selected."
                "(%s < %s)" % (n_features, self.components.shape[0]))

        X_new = X[:, self.components]

        assert_equal(
            X_new.shape,
            (n_samples, self.n_components),
            err_msg=("An error has occurred: The transformed X does "
                     "not have the proper shape."))
        return X_new

    #def fit_transform(self, X, y):
    #inherited from TransformerMixin

    def get_params(self):
        pass

    def set_params(self):
        pass


def make_submission():

    # Fill in your details here to be posted to the login form.
    payload = {
        'UserName': 'vwegmayr@inf.ethz.ch',
        'Password': 'cy9oSh8Kvs',
        "RememberMe": "false"
    }

    """
    # Use 'with' to ensure the session context is closed after use.
    with requests.Session() as s:
        p = s.post("https://www.kaggle.com/account/login", data=payload)

        print(p.url)
        
        data= {
        "SubmissionUpload":"/home/vwegmayr/ETH/Neuro/oasis_data/ml-project/data/sampleSubmission_1.csv"
        }

        r = requests.post("https://inclass.kaggle.com/c/mlp1/submissions/accept",
        data=data)

        print(r.text)
    """

    r = requests.post("https://inclass.kaggle.com/account/login", data=payload)
    print(r.text)


"""
def load_data(path):
    return pickle.load(open(path, "rb"))


def save_data(data, path):
     return pickle.dump(data, open(path, "wb"))


class Data(object):
    def __init__(self, X=None, y=None, pipe_X=None, pipe_y=None):
        if self.check_pipe(X, pipe_X):
            self.X = X
            self.pipe_X = pipe_X
        if self.check_pipe(y, pipe_y):
            self.y = y
            self.pipe_y = pipe_y

    def check_pipe(X, pipe):
        pipe.transform(X)
"""

if __name__=="__main__":
    make_submission()