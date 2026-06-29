import unittest

from tests.eval.dictation_ai.benchmark.sbd_lifecycle_scoring import score_boundary_granularity_adjusted


class DictationAiSbdLifecycleScoringTest(unittest.TestCase):
    def test_boundary_granularity_adjusted_accepts_split_actual_final(self) -> None:
        score = score_boundary_granularity_adjusted(
            ["그게 사실인지 아닌지 일단 미심이 별로 좋지는 않은데요."],
            ["그게 사실인지 아닌지", "일단 미심이 별로 좋지는 않은데요."],
        )

        self.assertEqual(score["precision"], 1.0)
        self.assertEqual(score["recall"], 1.0)
        self.assertEqual(score["f1"], 1.0)
        self.assertEqual(score["split_support_count"], 1)
        self.assertEqual(score["merge_support_count"], 0)

    def test_boundary_granularity_adjusted_accepts_merged_actual_final(self) -> None:
        score = score_boundary_granularity_adjusted(
            ["기준금리를 함부로 올릴 수는 없는데요.", "베트남도 인플레이션을 통제해야 합니다."],
            ["기준금리를 함부로 올릴 수는 없는데요. 베트남도 인플레이션을 통제해야 합니다."],
        )

        self.assertEqual(score["precision"], 1.0)
        self.assertEqual(score["recall"], 1.0)
        self.assertEqual(score["f1"], 1.0)
        self.assertEqual(score["split_support_count"], 0)
        self.assertEqual(score["merge_support_count"], 1)
