import numpy as np
from scipy.stats import pearsonr as sp_pearson


def MS_R(Y):
    n, k = Y.shape
    df = n - 1
    mu = np.mean(Y)
    ss = k * np.sum((np.mean(Y, axis=1) - mu)**2)

    return ss / df


def MS_W(Y):
    n, k = Y.shape
    df = n * (k - 1)
    A = np.reshape(np.mean(Y, axis=1), (-1, 1))
    ss = np.sum((Y - A)**2)

    return ss / df


def np_kl(p, q, eps=0.000001):
    p += eps
    p = p / np.sum(p)

    q += eps
    q = q / np.sum(q)

    return - np.sum(p * np.log(q / p))


def MS_E(Y):
    n, k = Y.shape
    df = (n - 1) * (k - 1)
    mu = np.mean(Y)
    row_means = np.reshape(np.mean(Y, axis=1), (-1, 1))
    col_means = np.reshape(np.mean(Y, axis=0), (1, -1))
    ss = 0

    ss = np.sum((Y - col_means - row_means + mu)**2)

    return ss / df


def MS_C(Y):
    n, k = Y.shape
    df = k - 1
    mu = np.mean(Y)
    ss = n * np.sum((np.mean(Y, axis=0) - mu)**2)

    return ss / df


def ICC_C1(Y):
    # special case
    if np.array_equal(Y[:, 0], Y[:, 1]):
        return 1

    k = Y.shape[1]
    MSR = MS_R(Y)
    MSE = MS_E(Y)
    if MSR == 0 and MSE == 0:
        return 1

    return (MSR - MSE) / (MSR + (k - 1) * MSE)


def ICC_A1(Y):
    n, k = Y.shape

    # special case:
    if np.array_equal(Y[:, 0], Y[:, 1]):
        return 1

    MSR = MS_R(Y)
    MSE = MS_E(Y)
    MSC = MS_C(Y)

    return (MSR - MSE) / (MSR + (k - 1) * MSE + k / n * (MSC - MSE))


def per_feature_ICC(test, retest, icc_func):
    n_features = test.shape[1]

    iccs = []
    for i in range(n_features):
        Y_1 = np.reshape(test[:, i], (-1, 1))
        Y_2 = np.reshape(retest[:, i], (-1, 1))
        Y = np.hstack((Y_1, Y_2))
        icc = icc_func(Y)
        iccs.append(icc)

    return np.array(iccs)


def kl_divergence(p, q, eps=0.000001):
    p += eps
    p = p / np.sum(p)

    q += eps
    q = q / np.sum(q)

    return - np.sum(p * np.log(q / p))


def js_divergence(p, q, eps=0.000001):
    m = 0.5 * (p + q)
    js = 0.5 * kl_divergence(p, m) + 0.5 * kl_divergence(q, m)

    return js


# Lin's Concordance Correlation Coefficient
def linccc(Y):
    """
    Arg:
        - Y: array of size (n_subjects, 2)
    """
    # special case
    if np.array_equal(Y[:, 0], Y[:, 1]):
        return 1

    mu_Y_1 = np.mean(Y[:, 0])
    mu_Y_2 = np.mean(Y[:, 1])
    S_1_sq = np.mean((Y[:, 0] - mu_Y_1) ** 2)
    S_2_sq = np.mean((Y[:, 1] - mu_Y_2) ** 2)
    S_12 = np.mean((Y[:, 0] - mu_Y_1) * (Y[:, 1] - mu_Y_2))

    num = 2 * S_12
    denom = (S_1_sq + S_2_sq + (mu_Y_1 - mu_Y_2)**2)

    if (num == denom == 0):
        return 1

    ccc_est = num / denom

    return ccc_est


def pearsonr(Y):
    # special case
    if np.array_equal(Y[:, 0], Y[:, 1]):
        return 1

    r, p = sp_pearson(Y[:, 0], Y[:, 1])
    return r
