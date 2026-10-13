"""Pure tests for bounded metric pick consensus."""
import importlib
import unittest

import numpy as np

from src.vision.visual_pick_estimator import GridTarget


def consensus_module():
    return importlib.import_module('src.vision.pick_consensus')


def target(x_mm=0., y_mm=0., confidence=.9):
    return GridTarget(4+x_mm/31.25, 4+y_mm/31.25, confidence, np.hypot(x_mm, y_mm)/31.25)


class MetricConsensusTests(unittest.TestCase):
    def select(self, values, **kwargs):
        return consensus_module().select_consensus(values, **kwargs)

    def test_coherent_two_of_three_ignores_early_confident_outlier(self):
        result = self.select([target(14, confidence=.99), target(.2, confidence=.6), target(.4, confidence=.7)])
        self.assertIsNotNone(result.target)
        self.assertEqual(result.support, (1, 2))
        self.assertEqual(result.valid_count, 3)
        self.assertAlmostEqual((result.target.col-4)*31.25, .3)

    def test_strict_majority_recovery_keeps_original_attempt_indices(self):
        result = self.select([None, target(14), target(-.2), target(.2), None, target(.1)])
        self.assertEqual(result.support, (2, 3, 5))
        self.assertEqual(result.valid_count, 4)
        self.assertAlmostEqual((result.target.col-4)*31.25, .1)

    def test_latest_outlier_or_missing_observation_vetoes_earlier_agreement(self):
        for values in ([target(0), target(.2), target(14)], [target(0), target(.2), None]):
            with self.subTest(values=values):
                result = self.select(values)
                self.assertIsNone(result.target)

    def test_tied_maximum_support_is_rejected_even_if_latest_is_in_one_group(self):
        result = self.select([target(0), target(4), target(8)])
        self.assertIsNone(result.target)
        self.assertTrue(result.reason)

    def test_separated_groups_have_no_strict_majority(self):
        result = self.select([target(0), target(.2), target(14), target(14.2)])
        self.assertIsNone(result.target)

    def test_transitive_chain_cannot_create_a_wide_cluster(self):
        result = self.select([target(0), target(6), target(12)])
        self.assertIsNone(result.target)

    def test_chain_inside_median_radius_is_not_rejected(self):
        self.assertIsNotNone(self.select([target(0), target(3), target(6)]).target)

    def test_larger_old_group_cannot_be_replaced_with_latest_smaller_group(self):
        result = self.select([target(0), target(.1), target(.2), target(14), target(14.1)])
        self.assertIsNone(result.target)
        self.assertEqual(result.support, (0, 1, 2))

    def test_metric_radius_boundary_is_inclusive_and_next_step_rejected(self):
        result = self.select([target(0), target(7.5)])
        self.assertIsNotNone(result.target)
        self.assertAlmostEqual((result.target.col-4)*31.25, 3.75)
        self.assertIsNone(self.select([target(0), target(7.501)]).target)

    def test_metric_distance_not_grid_or_independent_axis_cutoff(self):
        self.assertIsNone(self.select([target(0, 0), target(6, 6)]).target)
        # Non-square pitch makes the same grid delta physically larger in Y.
        values = [GridTarget(4, 4, .9, 0), GridTarget(4, 4.2, .9, .2)]
        self.assertIsNone(self.select(values, pitch_mm=(31.25, 40.)).target)

    def test_empty_or_only_none_has_no_authority(self):
        for values in ([], [None], [None, None, None], [target()]):
            with self.subTest(values=values):
                self.assertIsNone(self.select(values).target)

    def test_nonfinite_observation_or_invalid_limits_raise_not_soft_consensus(self):
        bad = [GridTarget(float('nan'), 4, .9, 0), GridTarget(4, float('inf'), .9, 0),
               GridTarget(4, 4, float('nan'), 0), GridTarget(4, 4, .9, float('nan'))]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.select([target(), value])
        for kwargs in ({'radius_mm': 0}, {'radius_mm': float('nan')},
                       {'pitch_mm': (0, 31.25)}, {'min_samples': 1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.select([target(), target()], **kwargs)


