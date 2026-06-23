import unittest

from tests.eval.dictation_ai.representative.select_sbd_representative_sources import (
    eligible_file_summaries,
    select_representative_sources,
)


def _file_summary(path: str, language: str, *, runtime: bool = True) -> dict[str, object]:
    payload: dict[str, object] = {
        "path": path,
        "line_count": 10,
        "timestamped_line_count": 10,
        "first_timestamp": "2026-06-20 00:00:00",
        "last_timestamp": "2026-06-20 00:10:00",
        "language_counts": {language: 5},
        "marker_counts": {
            "stt_raw": 5,
            "transcript": 3,
            "finalize_event": 2,
        },
    }
    if runtime:
        payload.update(
            {
                "stt_backend_counts": {"faster-whisper": 1},
                "stt_model_counts": {"large-v3": 1},
                "boundary_backend_counts": {"sat": 10},
                "boundary_model_counts": {"sat-3l-sm": 1},
                "translation_backend_counts": {"nllb-transformers": 1},
                "translation_model_counts": {"facebook/nllb-200-distilled-600M": 1},
                "window_seconds_counts": {"20.0": 1},
                "step_seconds_counts": {"1.0": 1},
                "sentence_finalize_age_counts": {"3": 1},
            }
        )
    return payload


class DictationAiSbdRepresentativeSourceSelectorTest(unittest.TestCase):
    def test_selects_deterministic_per_language_review_sources(self) -> None:
        audit = {
            "source_count": 4,
            "first_timestamp": "2026-06-20 00:00:00",
            "last_timestamp": "2026-06-20 00:40:00",
            "representative_readiness": {"can_seed_representative_candidates": True},
            "files": [
                _file_summary("logs/en-a.log", "en"),
                _file_summary("logs/en-b.log", "en"),
                _file_summary("logs/ko-a.log", "ko"),
                _file_summary("logs/zh-a.log", "zh"),
            ],
        }

        first = select_representative_sources(audit, per_language=1, seed="fixed-seed")
        second = select_representative_sources(audit, per_language=1, seed="fixed-seed")

        self.assertEqual(first, second)
        self.assertEqual(first["selected_source_count"], 3)
        self.assertEqual(first["eligible_source_counts"], {"en": 2, "ko": 1, "zh": 1})
        self.assertEqual(first["selected_source_counts"], {"en": 1, "ko": 1, "zh": 1})
        for record in first["selected_sources"]:
            self.assertEqual(record["corpus_role"], "representative")
            self.assertEqual(record["sampling_unit"], "session-window")
            self.assertEqual(record["review_status"], "requires_expected_final_review")
            self.assertIn("stt_backend_candidates", record)
            self.assertIn("window_seconds_candidates", record)
        self.assertFalse(first["interpretation"]["paper_evidence"])
        self.assertFalse(first["interpretation"]["case_generation"])
        self.assertTrue(first["interpretation"]["requires_human_expected_final"])

    def test_runtime_metadata_filter_rejects_partial_source_by_default(self) -> None:
        audit = {
            "files": [
                _file_summary("logs/en-complete.log", "en", runtime=True),
                _file_summary("logs/en-partial.log", "en", runtime=False),
            ]
        }

        eligible_default = eligible_file_summaries(
            audit,
            require_runtime_metadata=True,
            require_single_runtime=True,
        )
        eligible_relaxed = eligible_file_summaries(
            audit,
            require_runtime_metadata=False,
            require_single_runtime=False,
        )

        self.assertEqual([item["path"] for item in eligible_default], ["logs/en-complete.log"])
        self.assertEqual(
            [item["path"] for item in eligible_relaxed],
            ["logs/en-complete.log", "logs/en-partial.log"],
        )

    def test_rejects_sources_without_required_markers(self) -> None:
        incomplete = _file_summary("logs/en.log", "en")
        incomplete["marker_counts"] = {"stt_raw": 1, "transcript": 1}
        audit = {"files": [incomplete]}

        manifest = select_representative_sources(audit, per_language=1, seed="fixed-seed")

        self.assertEqual(manifest["selected_source_count"], 0)
        self.assertEqual(manifest["eligible_source_counts"], {})

    def test_default_filter_rejects_mixed_runtime_source(self) -> None:
        mixed = _file_summary("logs/en-mixed.log", "en")
        mixed["window_seconds_counts"] = {"10.0": 1, "20.0": 1}
        audit = {"files": [mixed]}

        strict = select_representative_sources(audit, per_language=1, seed="fixed-seed")
        relaxed = select_representative_sources(
            audit,
            per_language=1,
            seed="fixed-seed",
            require_single_runtime=False,
        )

        self.assertEqual(strict["selected_source_count"], 0)
        self.assertEqual(relaxed["selected_source_count"], 1)

    def test_priority_metric_selects_ranked_sources_before_hash_order(self) -> None:
        audit = {
            "target_collection_source_ranking": {
                "rankings": {
                    "stage_replace_deferred_per_stt_raw": [
                        {"path": "logs/zh-b.log", "ratio": 2.0, "count": 20},
                        {"path": "logs/zh-a.log", "ratio": 1.0, "count": 10},
                    ]
                }
            },
            "files": [
                _file_summary("logs/zh-a.log", "zh"),
                _file_summary("logs/zh-b.log", "zh"),
                _file_summary("logs/zh-unranked.log", "zh"),
            ],
        }

        manifest = select_representative_sources(
            audit,
            per_language=2,
            seed="fixed-seed",
            priority_metric="stage_replace_deferred_per_stt_raw",
        )

        self.assertEqual(manifest["priority_metric"], "stage_replace_deferred_per_stt_raw")
        self.assertTrue(manifest["interpretation"]["targeted_collection"])
        self.assertEqual(manifest["selected_source_count"], 2)
        self.assertEqual(
            [record["source_log"] for record in manifest["selected_sources"]],
            ["logs/zh-b.log", "logs/zh-a.log"],
        )
        self.assertEqual([record["priority_rank"] for record in manifest["selected_sources"]], [0, 1])
        self.assertEqual([record["priority_ratio"] for record in manifest["selected_sources"]], [2.0, 1.0])

    def test_priority_metric_rejects_missing_ranking(self) -> None:
        with self.assertRaises(ValueError):
            select_representative_sources(
                {"target_collection_source_ranking": {"rankings": {}}, "files": []},
                per_language=1,
                seed="fixed-seed",
                priority_metric="stage_replace_deferred_per_stt_raw",
            )


if __name__ == "__main__":
    unittest.main()
