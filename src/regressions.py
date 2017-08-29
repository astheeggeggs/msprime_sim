# Estimators of heritability and genetic correlation.

from __future__ import division
import numpy as np
import pandas as pd
from scipy.stats import norm, chi2
import jackknife as jk
from irwls import IRWLS
from scipy.stats import t as tdist
from collections import namedtuple
np.seterr(divide='raise', invalid='raise')

s = lambda x: remove_brackets(str(np.matrix(x)))

def update_separators(s, ii):
    '''s are separators with ii masked. Returns unmasked separators.'''
    maplist = np.arange(len(ii))[np.squeeze(ii)]
    mask_to_unmask = lambda i: maplist[i]
    t = np.apply_along_axis(mask_to_unmask, 0, s[1:-1])
    t = np.hstack(((0), t, (len(ii))))
    return t

def remove_brackets(x):
    '''Get rid of brackets and trailing whitespace in numpy arrays.'''
    return x.replace('[', '').replace(']', '').strip()

def append_intercept(x):
    '''
    Appends an intercept term to the design matrix for a linear regression.

    Parameters
    ----------
    x : np.matrix with shape (n_row, n_col)
        Design matrix. Columns are predictors; rows are observations.

    Returns
    -------
    x_new : np.matrix with shape (n_row, n_col+1)
        Design matrix with intercept term appended.

    '''
    n_row = x.shape[0]
    intercept = np.ones((n_row, 1))
    x_new = np.concatenate((x, intercept), axis=1)
    return x_new

def remove_intercept(x):
    '''Removes the last column.'''
    n_col = x.shape[1]
    return x[:, 0:n_col - 1]

def h2_obs_to_liab(h2_obs, P, K):
    '''
    Converts heritability on the observed scale in an ascertained sample to heritability
    on the liability scale in the population.

    Parameters
    ----------
    h2_obs : float
        Heritability on the observed scale in an ascertained sample.
    P : float in (0,1)
        Prevalence of the phenotype in the sample.
    K : float in (0,1)
        Prevalence of the phenotype in the population.

    Returns
    -------
    h2_liab : float
        Heritability of liability in the population.

    '''
    if np.isnan(P) and np.isnan(K):
        return h2_obs
    if K <= 0 or K >= 1:
        raise ValueError('K must be in the range (0,1)')
    if P <= 0 or P >= 1:
        raise ValueError('P must be in the range (0,1)')

    thresh = norm.isf(K)
    conversion_factor = K ** 2 * \
        (1 - K) ** 2 / (P * (1 - P) * norm.pdf(thresh) ** 2)
    return h2_obs * conversion_factor

class LD_Score_Regression(object):

    def __init__(self, y, x, w, N, M, n_blocks, intercept=None, slow=False, step1_ii=None, old_weights=False):
        for i in [y, x, w, M, N]:
            try:
                if len(i.shape) != 2:
                    raise TypeError('Arguments must be 2D arrays.')
            except AttributeError:
                raise TypeError('Arguments must be arrays.')

        n_snp, self.n_annot = x.shape
        if any(i.shape != (n_snp, 1) for i in [y, w, N]):
            raise ValueError(
                'N, weights and response (z1z2 or chisq) must have shape (n_snp, 1).')
        if M.shape != (1, self.n_annot):
            raise ValueError('M must have shape (1, n_annot).')

        M_tot = float(np.sum(M))
        x_tot = np.sum(x, axis=1).reshape((n_snp, 1))
        
        self.constrain_intercept = intercept is not None
        self.intercept = intercept
        self.n_blocks = n_blocks
        
        tot_agg = self.aggregate(y, x_tot, N, M_tot, intercept)
        initial_w = self._update_weights(x_tot, w, N, M_tot, tot_agg, intercept)
        
        Nbar = np.mean(N)  # keep condition number low
        x = np.multiply(N, x) / Nbar
        
        if not self.constrain_intercept:
            x, x_tot = append_intercept(x), append_intercept(x_tot)
            yp = y
        else:
            yp = y - intercept
            self.intercept_se = 'NA'
        
        del y
        
        self.twostep_filtered = None
        
        if step1_ii is not None and self.constrain_intercept:
            raise ValueError(
                'twostep is not compatible with constrain_intercept.')
        elif step1_ii is not None and self.n_annot > 1:
            raise ValueError(
                'twostep not compatible with partitioned LD Score yet.')
        elif step1_ii is not None:
            n1 = np.sum(step1_ii)
            self.twostep_filtered = n_snp - n1
            x1 = x[np.squeeze(step1_ii), :]
            yp1, w1, N1, initial_w1 = map(
                lambda a: a[step1_ii].reshape((n1, 1)), (yp, w, N, initial_w))
            update_func1 = lambda a: self._update_func(
                a, x1, w1, N1, M_tot, Nbar, ii=step1_ii)
            step1_jknife = IRWLS(
                x1, yp1, update_func1, n_blocks, slow=slow, w=initial_w1)
            step1_int, _ = self._intercept(step1_jknife)
            yp = yp - step1_int
            x = remove_intercept(x)
            x_tot = remove_intercept(x_tot)
            update_func2 = lambda a: self._update_func(
                a, x_tot, w, N, M_tot, Nbar, step1_int)
            s = update_separators(step1_jknife.separators, step1_ii)
            step2_jknife = IRWLS(
                x, yp, update_func2, n_blocks, slow=slow, w=initial_w, separators=s)
            c = np.sum(np.multiply(initial_w, x)) / \
                np.sum(np.multiply(initial_w, np.square(x)))
            jknife = self._combine_twostep_jknives(
                step1_jknife, step2_jknife, M_tot, c, Nbar)
        elif old_weights:
            initial_w = np.sqrt(initial_w)
            x = IRWLS._weight(x, initial_w)
            y = IRWLS._weight(yp, initial_w)
            jknife = jk.LstsqJackknifeFast(x, y, n_blocks)
        else:
            update_func = lambda a: self._update_func(
                a, x_tot, w, N, M_tot, Nbar, intercept)
            jknife = IRWLS(
                x, yp, update_func, n_blocks, slow=slow, w=initial_w)

        self.coef, self.coef_cov, self.coef_se = self._coef(jknife, Nbar)
        self.cat, self.cat_cov, self.cat_se =\
            self._cat(jknife, M, Nbar, self.coef, self.coef_cov)

        self.tot, self.tot_cov, self.tot_se = self._tot(self.cat, self.cat_cov)
        self.prop, self.prop_cov, self.prop_se =\
            self._prop(jknife, M, Nbar, self.cat, self.tot)

        self.enrichment, self.M_prop = self._enrichment(
            M, M_tot, self.cat, self.tot)
        if not self.constrain_intercept:
            self.intercept, self.intercept_se = self._intercept(jknife)

        self.jknife = jknife
        self.tot_delete_values = self._delete_vals_tot(jknife, Nbar, M)
        if not self.constrain_intercept:
            self.intercept_delete_values = jknife.delete_values[
                :, self.n_annot]

        self.M = M

    @classmethod
    def aggregate(cls, y, x, N, M, intercept=None):
        if intercept is None:
            intercept = cls.__null_intercept__

        num = M * (np.mean(y) - intercept)
        denom = np.mean(np.multiply(x, N))
        return num / denom

    def _update_func(self, x, ref_ld_tot, w_ld, N, M, Nbar, intercept=None, ii=None):
        raise NotImplementedError

    def _delete_vals_tot(self, jknife, Nbar, M):
        '''Get delete values for total h2 or gencov.'''
        n_annot = self.n_annot
        tot_delete_vals = jknife.delete_values[:, 0:n_annot]  # shape (n_blocks, n_annot)
        # shape (n_blocks, 1)
        tot_delete_vals = np.dot(tot_delete_vals, M.T) / Nbar
        return tot_delete_vals

    def _coef(self, jknife, Nbar):
        '''Get coefficient estimates + cov from the jackknife.'''
        n_annot = self.n_annot
        coef = jknife.est[0, 0:n_annot] / Nbar
        coef_cov = jknife.jknife_cov[0:n_annot, 0:n_annot] / Nbar ** 2
        coef_se = np.sqrt(np.diag(coef_cov))
        return coef, coef_cov, coef_se

    def _cat(self, jknife, M, Nbar, coef, coef_cov):
        '''Convert coefficients to per-category h2 or gencov.'''
        cat = np.multiply(M, coef)
        cat_cov = np.multiply(np.dot(M.T, M), coef_cov)
        cat_se = np.sqrt(np.diag(cat_cov))
        return cat, cat_cov, cat_se

    def _tot(self, cat, cat_cov):
        '''Convert per-category h2 to total h2 or gencov.'''
        tot = np.sum(cat)
        tot_cov = np.sum(cat_cov)
        tot_se = np.sqrt(tot_cov)
        return tot, tot_cov, tot_se

    def _prop(self, jknife, M, Nbar, cat, tot):
        '''Convert total h2 and per-category h2 to per-category proportion h2 or gencov.'''
        n_annot = self.n_annot
        n_blocks = jknife.delete_values.shape[0]
        numer_delete_vals = np.multiply(
            M, jknife.delete_values[:, 0:n_annot]) / Nbar  # (n_blocks, n_annot)
        denom_delete_vals = np.sum(
            numer_delete_vals, axis=1).reshape((n_blocks, 1))
        denom_delete_vals = np.dot(denom_delete_vals, np.ones((1, n_annot)))
        prop = jk.RatioJackknife(
            cat / tot, numer_delete_vals, denom_delete_vals)
        return prop.est, prop.jknife_cov, prop.jknife_se

    def _enrichment(self, M, M_tot, cat, tot):
        '''Compute proportion of SNPs per-category enrichment for h2 or gencov.'''
        M_prop = M / M_tot
        enrichment = np.divide(cat, M) / (tot / M_tot)
        return enrichment, M_prop

    def _intercept(self, jknife):
        '''Extract intercept and intercept SE from block jackknife.'''
        n_annot = self.n_annot
        intercept = jknife.est[0, n_annot]
        intercept_se = jknife.jknife_se[0, n_annot]
        return intercept, intercept_se

    def _combine_twostep_jknives(self, step1_jknife, step2_jknife, M_tot, c, Nbar=1):
        '''Combine free intercept and constrained intercept jackknives for --two-step.'''
        n_blocks, n_annot = step1_jknife.delete_values.shape
        n_annot -= 1
        if n_annot > 2:
            raise ValueError(
                'twostep not yet implemented for partitioned LD Score.')

        step1_int, _ = self._intercept(step1_jknife)
        est = np.hstack(
            (step2_jknife.est, np.array(step1_int).reshape((1, 1))))
        delete_values = np.zeros((n_blocks, n_annot + 1))
        delete_values[:, n_annot] = step1_jknife.delete_values[:, n_annot]
        delete_values[:, 0:n_annot] = step2_jknife.delete_values -\
            c * (step1_jknife.delete_values[:, n_annot] -
                 step1_int).reshape((n_blocks, n_annot))  # check this
        pseudovalues = jk.Jackknife.delete_values_to_pseudovalues(
            delete_values, est)
        jknife_est, jknife_var, jknife_se, jknife_cov = jk.Jackknife.jknife(
            pseudovalues)
        jknife = namedtuple('jknife',
                            ['est', 'jknife_se', 'jknife_est', 'jknife_var', 'jknife_cov', 'delete_values'])
        return jknife(est, jknife_se, jknife_est, jknife_var, jknife_cov, delete_values)

class Hsq(LD_Score_Regression):

    __null_intercept__ = 1

    def __init__(self, y, x, w, N, M, n_blocks=200, intercept=None, slow=False, twostep=None, old_weights=False):
        step1_ii = None
        if twostep is not None:
            step1_ii = y < twostep

        LD_Score_Regression.__init__(self, y, x, w, N, M, n_blocks, intercept=intercept,
                                     slow=slow, step1_ii=step1_ii, old_weights=old_weights)
        self.mean_chisq, self.lambda_gc = self._summarize_chisq(y)
        if not self.constrain_intercept:
            self.ratio, self.ratio_se = self._ratio(
                self.intercept, self.intercept_se, self.mean_chisq)

    def _update_func(self, x, ref_ld_tot, w_ld, N, M, Nbar, intercept=None, ii=None):
        '''
        Update function for IRWLS

        x is the output of np.linalg.lstsq.
        x[0] is the regression coefficients
        x[0].shape is (# of dimensions, 1)
        the last element of x[0] is the intercept.

        intercept is None --> free intercept
        intercept is not None --> constrained intercept
        '''
        hsq = M * x[0][0] / Nbar
        if intercept is None:
            intercept = max(x[0][1])  # divide by zero error if intercept < 0
        else:
            if ref_ld_tot.shape[1] > 1:
                raise ValueError(
                    'Design matrix has intercept column for constrained intercept regression!')

        ld = ref_ld_tot[:, 0].reshape(w_ld.shape)  # remove intercept
        w = self.weights(ld, w_ld, N, M, hsq, intercept, ii)
        return w

    def _summarize_chisq(self, chisq):
        '''Compute mean chi^2 and lambda_GC.'''
        mean_chisq = np.mean(chisq)
        # median and matrix don't play nice
        lambda_gc = np.median(np.asarray(chisq)) / 0.4549
        return mean_chisq, lambda_gc

    def _ratio(self, intercept, intercept_se, mean_chisq):
        '''Compute ratio (intercept - 1) / (mean chi^2 -1 ).'''
        if mean_chisq > 1:
            ratio_se = intercept_se / (mean_chisq - 1)
            ratio = (intercept - 1) / (mean_chisq - 1)
        else:
            ratio = 'NA'
            ratio_se = 'NA'

        return ratio, ratio_se

    def summary(self, ref_ld_colnames=None, P=None, K=None, overlap=False):
        '''Print summary of the LD Score Regression.'''
        if P is not None and K is not None:
            T = 'Liability'
            c = h2_obs_to_liab(1, P, K)
        else:
            T = 'Observed'
            c = 1

        out = ['Total ' + T + ' scale h2: ' +
               s(c * self.tot) + ' (' + s(c * self.tot_se) + ')']

        out.append('Lambda GC: ' + s(self.lambda_gc))
        out.append('Mean Chi^2: ' + s(self.mean_chisq))
        if self.constrain_intercept:
            out.append(
                'Intercept: constrained to {C}'.format(C=s(self.intercept)))
        else:
            out.append(
                'Intercept: ' + s(self.intercept) + ' (' + s(self.intercept_se) + ')')
            if self.mean_chisq > 1:
                if self.ratio < 0:
                    out.append(
                      'Ratio < 0 (usually indicates GC correction).')
                else:
                    out.append(
                      'Ratio: ' + s(self.ratio) + ' (' + s(self.ratio_se) + ')')
            else:
                out.append('Ratio: NA (mean chi^2 < 1)')

        return remove_brackets('\n'.join(out))

    def _update_weights(self, ld, w_ld, N, M, hsq, intercept, ii=None):
        if intercept is None:
            intercept = self.__null_intercept__

        return self.weights(ld, w_ld, N, M, hsq, intercept, ii)

    @classmethod
    def weights(cls, ld, w_ld, N, M, hsq, intercept=None, ii=None):
        '''
        Regression weights.

        Parameters
        ----------
        ld : np.matrix with shape (n_snp, 1)
            LD Scores (non-partitioned).
        w_ld : np.matrix with shape (n_snp, 1)
            LD Scores (non-partitioned) computed with sum r^2 taken over only those SNPs included
            in the regression.
        N : >np.matrix of ints > 0 with shape (n_snp, 1)
            Number of individuals sampled for each SNP.
        M : float > 0
            Number of SNPs used for estimating LD Score (need not equal number of SNPs included in
            the regression).
        hsq : float in [0,1]
            Heritability estimate.

        Returns
        -------
        w : np.matrix with shape (n_snp, 1)
            Regression weights. Approx equal to reciprocal of conditional variance function.

        '''
        M = float(M)
        if intercept is None:
            intercept = 1

        hsq = max(hsq, 0.0)
        hsq = min(hsq, 1.0)
        ld = np.fmax(ld, 1.0)
        w_ld = np.fmax(w_ld, 1.0)
        c = hsq * N / M

        # print 'intercept: {i}'.format(i=intercept)
        # print np.multiply(c,ld)
        # print 'c:{c}'.format(c=c)
        # print ld
        # print intercept + np.multiply(c,ld)
        # print np.square(intercept + np.multiply(c, ld))
        # print 2 * np.square(intercept + np.multiply(c, ld))

        het_w = 1.0 / (2 * np.square(intercept + np.multiply(c, ld)))
        oc_w = 1.0 / w_ld
        w = np.multiply(het_w, oc_w)
        return w