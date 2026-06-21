import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch
from io import StringIO

from tests.eval.dictation_ai.sweeps.run_sbd_parameter_sweep import (
    SweepJob,
    build_evidence_protocol,
    build_sweep_jobs,
    build_summary_payload,
    _load_report_summary,
    parse_sweep_parameter,
    run_job,
    validate_sweep_execution_contract,
    validate_sweep_case_set,
)
from tests.eval.dictation_ai.sweeps.sbd_parameter_sweep_report import (
    attach_baseline_deltas,
    build_evidence_summary,
    missing_required_evidence_fields,
    render_markdown_summary,
)
from tests.eval.dictation_ai.benchmark.sbd_runtime_contract import lifecycle_replay_contract
from tests.eval.dictation_ai.sweeps.refresh_sbd_parameter_sweep_summary import (
    _default_refreshed_summary_path,
    expand_summary_paths as expand_refresh_summary_paths,
    main as refresh_summary_main,
    refresh_summary_payload,
)
from tests.eval.dictation_ai.sweeps.summarize_sbd_evidence_reports import complete_report_paths
from tests.eval.dictation_ai.sweeps.summarize_sbd_evidence_reports import render_markdown as render_evidence_markdown
from tests.eval.dictation_ai.sweeps.summarize_sbd_evidence_reports import summarize_reports
from tests.eval.dictation_ai.sweeps.validate_sbd_evidence_report import expand_report_paths, validate_report, validate_reports


class DictationAiSbdParameterSweepTest(unittest.TestCase):
    def _write_review_packets(
        self,
        path: Path,
        *,
        language: str = "ko",
        source_log: str = ".tmp/logs/avc-whisper.log",
        packet_id: str = "ko_representative_review_abc",
    ) -> None:
        payload = {
            "representative_review_packet_version": 1,
            "source_manifest": {
                "sampling_unit": "session-window",
                "sampling_rule": "session-hash-v1:test",
                "selected_source_count": 1,
                "selected_source_counts": {language: 1},
            },
            "packet_count": 1,
            "ready_packet_count": 1,
            "missing_source_logs": [],
            "packet_readiness_blockers": [],
            "interpretation": {
                "paper_evidence": False,
                "case_generation": False,
                "expected_final_generated": False,
            },
            "packets": [
                {
                    "id": packet_id,
                    "language": language,
                    "source_log": source_log,
                    "source_started_at": "2026-06-21 00:00:00",
                    "source_ended_at": "2026-06-21 00:01:00",
                    "source_window_filter": {
                        "applied": True,
                        "started_at": "2026-06-21 00:00:00",
                        "ended_at": "2026-06-21 00:01:00",
                    },
                    "event_counts": {
                        "raw_chunks": 1,
                        "transcripts": 1,
                        "final_events": 1,
                        "performance_events": 1,
                    },
                    "review_readiness": {
                        "ready_for_human_review": True,
                        "missing_event_kinds": [],
                    },
                    "paper_evidence": False,
                    "case_generation": False,
                    "expected_final_generated": False,
                }
            ],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")

    def test_accepts_manifest_parameter_override(self) -> None:
        parameter = parse_sweep_parameter("SENTENCE_CONFIRM_CHUNKS=3")

        self.assertEqual(parameter.name, "SENTENCE_CONFIRM_CHUNKS")
        self.assertEqual(parameter.value, "3")
        self.assertEqual(parameter.env_name, "AVC_DICTATION_SENTENCE_CONFIRM_CHUNKS")
        self.assertEqual(parameter.label, "sentence_confirm_chunks-3")

    def test_rejects_non_manifest_parameter(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported sweep parameter"):
            parse_sweep_parameter("LANGUAGE_SPECIFIC_REGEX=1")

    def test_rejects_wrong_parameter_value_type(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires an integer value"):
            parse_sweep_parameter("SENTENCE_CONFIRM_CHUNKS=loose")

        with self.assertRaisesRegex(ValueError, "between 0.0 and 1.0"):
            parse_sweep_parameter("REVISION_FALLBACK_COVERAGE_MIN=1.7")

    def test_rejects_parameter_outside_manifest_range(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be <="):
            parse_sweep_parameter("SENTENCE_CONFIRM_CHUNKS=99")

        with self.assertRaisesRegex(ValueError, "must be >="):
            parse_sweep_parameter("REVISION_FALLBACK_COVERAGE_MIN=0.1")

    def test_builds_cuda_float16_benchmark_jobs_with_same_cases(self) -> None:
        jobs = build_sweep_jobs(
            python="python",
            cases=(Path("cases-a.jsonl"), Path("cases-b.jsonl")),
            output_dir=Path("out"),
            parameters=(parse_sweep_parameter("SENTENCE_CONFIRM_CHUNKS=3"),),
            include_baseline=True,
        )

        self.assertEqual([job.label for job in jobs], ["baseline", "sentence_confirm_chunks-3"])
        for job in jobs:
            self.assertIn("--cases", job.argv)
            self.assertIn("cases-a.jsonl", job.argv)
            self.assertIn("cases-b.jsonl", job.argv)
            self.assertIn("--device", job.argv)
            self.assertIn("cuda", job.argv)
            self.assertIn("--compute-type", job.argv)
            self.assertIn("float16", job.argv)
        self.assertEqual(jobs[0].env_overrides, {})
        self.assertEqual(jobs[1].env_overrides, {"AVC_DICTATION_SENTENCE_CONFIRM_CHUNKS": "3"})

    def test_run_job_forces_offline_model_cache_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job = SweepJob(
                label="sentence_confirm_chunks-1",
                output=Path(tmp) / "report.json",
                argv=("python", "benchmark.py"),
                env_overrides={"AVC_DICTATION_SENTENCE_CONFIRM_CHUNKS": "1"},
            )

            with patch("tests.eval.dictation_ai.sweeps.run_sbd_parameter_sweep.subprocess.run") as run:
                run_job(job)

        env = run.call_args.kwargs["env"]
        self.assertEqual(env["HF_HUB_OFFLINE"], "1")
        self.assertEqual(env["TRANSFORMERS_OFFLINE"], "1")
        self.assertEqual(env["AVC_DICTATION_SENTENCE_CONFIRM_CHUNKS"], "1")

    def test_load_report_summary_includes_language_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "report.json"
            output.write_text(
                json.dumps(
                    {
                        "case_count": 2,
                        "corpus_role": "challenge-replay",
                        "summary": {"final_f1_avg": 0.5},
                        "language_summary": {"ko": {"case_count": 2, "final_f1_avg": 0.5}},
                        "tag_summary": {"missing-final": {"case_count": 2, "final_f1_avg": 0.5}},
                        "lifecycle_bottleneck_summary": {
                            "metrics": {"stage_replace_deferred": 3},
                            "by_language": {"ko": {"underfinal_count": 1}},
                        },
                        "evidence_strata_summary": {
                            "lifecycle_without_input_review": {"case_count": 2},
                        },
                        "staged_queue_residue_summary": {
                            "queue_residue_case_count": 1,
                            "queue_residue_total": 2,
                        },
                        "case_exemplar_summary": {
                            "lifecycle_focus_top": [
                                {
                                    "id": "case-heavy",
                                    "bottleneck_score": 12.0,
                                    "metrics": {"stage_queue_revision": 3},
                                }
                            ]
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            job = SweepJob(
                label="baseline",
                output=output,
                argv=("python", "benchmark.py"),
                env_overrides={},
            )

            summary = _load_report_summary(job)

            self.assertEqual(summary["language_summary"], {"ko": {"case_count": 2, "final_f1_avg": 0.5}})
            self.assertEqual(summary["corpus_role"], "challenge-replay")
            self.assertEqual(
                summary["tag_summary"],
                {"missing-final": {"case_count": 2, "final_f1_avg": 0.5}},
            )
            self.assertEqual(
                summary["lifecycle_bottleneck_summary"],
                {
                    "metrics": {"stage_replace_deferred": 3},
                    "by_language": {"ko": {"underfinal_count": 1}},
                },
            )
            self.assertEqual(
                summary["evidence_strata_summary"],
                {"lifecycle_without_input_review": {"case_count": 2}},
            )
            self.assertEqual(
                summary["staged_queue_residue_summary"],
                {"queue_residue_case_count": 1, "queue_residue_total": 2},
            )
            self.assertEqual(
                summary["case_exemplar_summary"]["lifecycle_focus_top"][0]["id"],
                "case-heavy",
            )

    def test_attach_baseline_deltas_to_metrics_and_languages(self) -> None:
        results = [
            {
                "label": "baseline",
                "env_overrides": {},
                "metrics": {"final_f1_avg": 0.5, "finalized_per_stage_start": 0.7},
                "language_summary": {
                    "ko": {"case_count": 2, "final_f1_avg": 0.5, "staged_residue_count": 3}
                },
                "tag_summary": {
                    "missing-final": {"case_count": 2, "final_f1_avg": 0.5, "staged_residue_count": 3}
                },
                "lifecycle_bottleneck_summary": {
                    "metrics": {"stage_replace_deferred": 5},
                    "replacement_decision_counts": {"unconfirmed": 5},
                    "deferred_replacement_decision_counts": {"unconfirmed": 5},
                    "quality_block_reason_counts": {"no_end_marker": 4},
                    "by_language": {"ko": {"underfinal_count": 4}},
                },
                "evidence_strata_summary": {
                    "lifecycle_without_input_review": {
                        "case_count": 9,
                        "final_f1_avg": 0.45,
                        "staged_residue_count": 4,
                    },
                    "input_contamination_review": {
                        "case_count": 1,
                        "final_f1_avg": 0.8,
                    },
                },
                "staged_queue_residue_summary": {
                    "queue_residue_case_count": 3,
                    "queue_residue_total": 6,
                    "queue_residue_avg_when_present": 2.0,
                    "queue_residue_max": 3,
                },
                "queue_residue_strata_summary": {
                    "no_queue": {"case_count": 6, "final_f1_avg": 0.6, "final_boundary_f1_avg": 0.3, "staged_residue_count": 1, "empty_final_count": 1, "metrics": {"stage_queue_revision": 1, "stage_replace_deferred": 2}},
                    "queue_len_1": {"case_count": 1, "final_f1_avg": 0.4, "final_boundary_f1_avg": 0.2, "staged_residue_count": 1, "empty_final_count": 0, "metrics": {"stage_queue_revision": 2, "stage_replace_deferred": 3}},
                    "queue_len_2_to_4": {"case_count": 2, "final_f1_avg": 0.3, "final_boundary_f1_avg": 0.1, "staged_residue_count": 2, "empty_final_count": 1, "metrics": {"stage_queue_revision": 4, "stage_replace_deferred": 5}},
                    "queue_len_ge_5": {"case_count": 0, "final_f1_avg": 0.0, "final_boundary_f1_avg": 0.0, "staged_residue_count": 0, "empty_final_count": 0, "metrics": {"stage_queue_revision": 0, "stage_replace_deferred": 0}},
                },
            },
            {
                "label": "sentence_confirm_chunks-1",
                "env_overrides": {"AVC_DICTATION_SENTENCE_CONFIRM_CHUNKS": "1"},
                "metrics": {"final_f1_avg": 0.6, "finalized_per_stage_start": 0.8},
                "language_summary": {
                    "ko": {"case_count": 2, "final_f1_avg": 0.4, "staged_residue_count": 1}
                },
                "tag_summary": {
                    "missing-final": {"case_count": 2, "final_f1_avg": 0.6, "staged_residue_count": 2}
                },
                "lifecycle_bottleneck_summary": {
                    "metrics": {"stage_replace_deferred": 3},
                    "replacement_decision_counts": {"unconfirmed": 3},
                    "deferred_replacement_decision_counts": {"unconfirmed": 3},
                    "quality_block_reason_counts": {"no_end_marker": 1},
                    "by_language": {"ko": {"underfinal_count": 2}},
                },
                "evidence_strata_summary": {
                    "lifecycle_without_input_review": {
                        "case_count": 9,
                        "final_f1_avg": 0.55,
                        "staged_residue_count": 2,
                    },
                    "input_contamination_review": {
                        "case_count": 1,
                        "final_f1_avg": 0.7,
                    },
                },
                "staged_queue_residue_summary": {
                    "queue_residue_case_count": 2,
                    "queue_residue_total": 4,
                    "queue_residue_avg_when_present": 2.0,
                    "queue_residue_max": 2,
                },
                "queue_residue_strata_summary": {
                    "no_queue": {"case_count": 7, "final_f1_avg": 0.7, "final_boundary_f1_avg": 0.4, "staged_residue_count": 0, "empty_final_count": 0, "metrics": {"stage_queue_revision": 1, "stage_replace_deferred": 1}},
                    "queue_len_1": {"case_count": 0, "final_f1_avg": 0.0, "final_boundary_f1_avg": 0.0, "staged_residue_count": 0, "empty_final_count": 0, "metrics": {"stage_queue_revision": 0, "stage_replace_deferred": 0}},
                    "queue_len_2_to_4": {"case_count": 2, "final_f1_avg": 0.35, "final_boundary_f1_avg": 0.1, "staged_residue_count": 2, "empty_final_count": 1, "metrics": {"stage_queue_revision": 3, "stage_replace_deferred": 4}},
                    "queue_len_ge_5": {"case_count": 0, "final_f1_avg": 0.0, "final_boundary_f1_avg": 0.0, "staged_residue_count": 0, "empty_final_count": 0, "metrics": {"stage_queue_revision": 0, "stage_replace_deferred": 0}},
                },
            },
        ]

        updated = attach_baseline_deltas(results)

        self.assertEqual(updated[0]["metric_deltas"], {"final_f1_avg": 0.0, "finalized_per_stage_start": 0.0})
        self.assertEqual(
            updated[0]["language_deltas"]["ko"],
            {"case_count": 0.0, "final_f1_avg": 0.0, "staged_residue_count": 0.0},
        )
        self.assertAlmostEqual(updated[1]["metric_deltas"]["final_f1_avg"], 0.1)
        self.assertAlmostEqual(updated[1]["metric_deltas"]["finalized_per_stage_start"], 0.1)
        self.assertAlmostEqual(updated[1]["language_deltas"]["ko"]["final_f1_avg"], -0.1)
        self.assertEqual(updated[1]["language_deltas"]["ko"]["staged_residue_count"], -2.0)
        self.assertAlmostEqual(updated[1]["tag_deltas"]["missing-final"]["final_f1_avg"], 0.1)
        self.assertEqual(updated[1]["tag_deltas"]["missing-final"]["staged_residue_count"], -1.0)
        self.assertEqual(updated[1]["lifecycle_bottleneck_deltas"]["metrics"]["stage_replace_deferred"], -2.0)
        self.assertEqual(
            updated[1]["lifecycle_bottleneck_deltas"]["replacement_decision_counts"]["unconfirmed"],
            -2.0,
        )
        self.assertEqual(
            updated[1]["lifecycle_bottleneck_deltas"]["deferred_replacement_decision_counts"]["unconfirmed"],
            -2.0,
        )
        self.assertEqual(
            updated[1]["lifecycle_bottleneck_deltas"]["quality_block_reason_counts"]["no_end_marker"],
            -3.0,
        )
        self.assertEqual(
            updated[1]["lifecycle_bottleneck_deltas"]["by_language"]["ko"]["underfinal_count"],
            -2.0,
        )
        self.assertEqual(
            updated[1]["evidence_strata_deltas"]["lifecycle_without_input_review"]["staged_residue_count"],
            -2.0,
        )
        self.assertAlmostEqual(
            updated[1]["evidence_strata_deltas"]["lifecycle_without_input_review"]["final_f1_avg"],
            0.1,
        )
        self.assertAlmostEqual(
            updated[1]["evidence_strata_deltas"]["input_contamination_review"]["final_f1_avg"],
            -0.1,
        )
        self.assertEqual(updated[1]["staged_queue_residue_deltas"]["queue_residue_case_count"], -1.0)
        self.assertEqual(updated[1]["staged_queue_residue_deltas"]["queue_residue_total"], -2.0)
        self.assertEqual(updated[1]["staged_queue_residue_deltas"]["queue_residue_max"], -1.0)
        self.assertEqual(updated[1]["queue_residue_strata_deltas"]["no_queue"]["case_count"], 1.0)
        self.assertAlmostEqual(updated[1]["queue_residue_strata_deltas"]["no_queue"]["final_f1_avg"], 0.1)
        self.assertEqual(
            updated[1]["queue_residue_strata_deltas"]["queue_len_2_to_4"]["metrics"]["stage_queue_revision"],
            -1.0,
        )

    def test_build_evidence_summary_keeps_compact_metric_language_and_key_tag_deltas(self) -> None:
        results = attach_baseline_deltas(
            [
                {
                    "label": "baseline",
                    "env_overrides": {},
                    "metrics": {
                        "final_precision_avg": 0.8,
                        "final_f1_avg": 0.5,
                        "final_boundary_f1_avg": 0.5,
                    },
                    "language_summary": {
                        "ko": {"final_precision_avg": 0.9, "final_f1_avg": 0.5, "staged_residue_count": 3}
                    },
                    "tag_summary": {
                        "missing-final": {
                            "case_count": 2,
                            "final_precision_avg": 0.8,
                            "final_f1_avg": 0.5,
                            "staged_residue_count": 3,
                        },
                        "topic-only": {"case_count": 2, "final_f1_avg": 0.1},
                    },
                    "lifecycle_bottleneck_summary": {
                        "metrics": {"stage_replace_deferred": 2, "stage_queue_revision": 5},
                        "replacement_decision_counts": {"unconfirmed": 2},
                        "deferred_replacement_decision_counts": {"unconfirmed": 2},
                        "quality_block_reason_counts": {"no_end_marker": 5},
                        "by_language": {"ko": {"underfinal_count": 1, "pending_residue_count": 3}},
                    },
                    "evidence_strata_summary": {
                        "lifecycle_without_input_review": {
                            "case_count": 10,
                            "final_f1_avg": 0.45,
                            "final_boundary_f1_avg": 0.20,
                            "staged_residue_count": 4,
                        },
                        "input_contamination_review": {
                            "case_count": 1,
                            "final_f1_avg": 0.8,
                            "final_boundary_f1_avg": 0.5,
                        },
                    },
                    "staged_queue_residue_summary": {
                        "queue_residue_case_count": 4,
                        "queue_residue_total": 8,
                        "queue_residue_avg_when_present": 2.0,
                        "queue_residue_max": 3,
                    },
                    "queue_residue_strata_summary": {
                        "no_queue": {
                            "case_count": 6,
                            "final_f1_avg": 0.6,
                            "final_boundary_f1_avg": 0.3,
                            "staged_residue_count": 1,
                            "empty_final_count": 1,
                            "metrics": {"stage_queue_revision": 1, "stage_replace_deferred": 2},
                        },
                        "queue_len_1": {
                            "case_count": 1,
                            "final_f1_avg": 0.4,
                            "final_boundary_f1_avg": 0.2,
                            "staged_residue_count": 1,
                            "empty_final_count": 0,
                            "metrics": {"stage_queue_revision": 2, "stage_replace_deferred": 3},
                        },
                        "queue_len_2_to_4": {
                            "case_count": 3,
                            "final_f1_avg": 0.3,
                            "final_boundary_f1_avg": 0.1,
                            "staged_residue_count": 3,
                            "empty_final_count": 1,
                            "metrics": {"stage_queue_revision": 4, "stage_replace_deferred": 5},
                        },
                        "queue_len_ge_5": {
                            "case_count": 0,
                            "final_f1_avg": 0.0,
                            "final_boundary_f1_avg": 0.0,
                            "staged_residue_count": 0,
                            "empty_final_count": 0,
                            "metrics": {"stage_queue_revision": 0, "stage_replace_deferred": 0},
                        },
                    },
                    "case_exemplar_summary": {
                        "lifecycle_focus_top": [
                            {
                                "id": "baseline-heavy",
                                "bottleneck_score": 10.0,
                                "final_f1": 0.2,
                                "final_boundary_f1": 0.0,
                                "metrics": {
                                    "stage_queue_revision": 3,
                                    "stage_replace_deferred": 5,
                                    "stage_candidate_quality_blocked": 2,
                                },
                            }
                        ]
                    },
                },
                {
                    "label": "revision_fallback_coverage_min-0.50",
                    "env_overrides": {"AVC_DICTATION_REVISION_FALLBACK_COVERAGE_MIN": "0.50"},
                    "metrics": {
                        "final_precision_avg": 0.7,
                        "final_f1_avg": 0.6,
                        "final_boundary_f1_avg": 0.4,
                    },
                    "language_summary": {
                        "ko": {"final_precision_avg": 0.7, "final_f1_avg": 0.4, "staged_residue_count": 5}
                    },
                    "tag_summary": {
                        "missing-final": {
                            "case_count": 2,
                            "final_precision_avg": 0.7,
                            "final_f1_avg": 0.3,
                            "staged_residue_count": 6,
                        },
                        "topic-only": {"case_count": 2, "final_f1_avg": 0.9},
                    },
                    "lifecycle_bottleneck_summary": {
                        "metrics": {"stage_replace_deferred": 5, "stage_queue_revision": 4},
                        "replacement_decision_counts": {"unconfirmed": 5},
                        "deferred_replacement_decision_counts": {"unconfirmed": 5},
                        "quality_block_reason_counts": {"no_end_marker": 2},
                        "by_language": {"ko": {"underfinal_count": 2, "pending_residue_count": 1}},
                    },
                    "evidence_strata_summary": {
                        "lifecycle_without_input_review": {
                            "case_count": 10,
                            "final_f1_avg": 0.55,
                            "final_boundary_f1_avg": 0.18,
                            "staged_residue_count": 3,
                        },
                        "input_contamination_review": {
                            "case_count": 1,
                            "final_f1_avg": 0.7,
                            "final_boundary_f1_avg": 0.45,
                        },
                    },
                    "staged_queue_residue_summary": {
                        "queue_residue_case_count": 3,
                        "queue_residue_total": 9,
                        "queue_residue_avg_when_present": 3.0,
                        "queue_residue_max": 5,
                    },
                    "queue_residue_strata_summary": {
                        "no_queue": {
                            "case_count": 7,
                            "final_f1_avg": 0.7,
                            "final_boundary_f1_avg": 0.4,
                            "staged_residue_count": 0,
                            "empty_final_count": 0,
                            "metrics": {"stage_queue_revision": 1, "stage_replace_deferred": 1},
                        },
                        "queue_len_1": {
                            "case_count": 0,
                            "final_f1_avg": 0.0,
                            "final_boundary_f1_avg": 0.0,
                            "staged_residue_count": 0,
                            "empty_final_count": 0,
                            "metrics": {"stage_queue_revision": 0, "stage_replace_deferred": 0},
                        },
                        "queue_len_2_to_4": {
                            "case_count": 2,
                            "final_f1_avg": 0.35,
                            "final_boundary_f1_avg": 0.1,
                            "staged_residue_count": 2,
                            "empty_final_count": 1,
                            "metrics": {"stage_queue_revision": 3, "stage_replace_deferred": 4},
                        },
                        "queue_len_ge_5": {
                            "case_count": 1,
                            "final_f1_avg": 0.1,
                            "final_boundary_f1_avg": 0.0,
                            "staged_residue_count": 1,
                            "empty_final_count": 1,
                            "metrics": {"stage_queue_revision": 6, "stage_replace_deferred": 7},
                        },
                    },
                    "case_exemplar_summary": {
                        "lifecycle_focus_top": [
                            {
                                "id": "override-heavy",
                                "bottleneck_score": 11.0,
                                "final_f1": 0.3,
                                "final_boundary_f1": 0.1,
                                "metrics": {
                                    "stage_queue_revision": 4,
                                    "stage_replace_deferred": 6,
                                    "stage_candidate_quality_blocked": 1,
                                },
                            }
                        ]
                    },
                },
            ]
        )

        summary = build_evidence_summary(results)

        self.assertIn("missing-final", summary["key_tags"])
        self.assertAlmostEqual(summary["results"][1]["metric_deltas"]["final_f1_avg"], 0.1)
        self.assertEqual(summary["results"][1]["language_deltas"]["ko"]["staged_residue_count"], 2.0)
        self.assertAlmostEqual(summary["results"][1]["key_tag_deltas"]["missing-final"]["final_f1_avg"], -0.2)
        self.assertEqual(
            summary["results"][1]["interpretation_flags"],
            [
                "overall-final-f1-up-precision-down",
                "overall-final-f1-up-boundary-down",
                "language-final-f1-regression",
                "language-precision-regression",
                "key-tag-precision-regression",
            ],
        )
        self.assertEqual(summary["results"][0]["adoption_review"], "baseline")
        self.assertEqual(summary["results"][1]["adoption_review"], "review-risk")
        self.assertEqual(
            summary["results"][1]["lifecycle_bottleneck_summary"]["metrics"],
            {"stage_replace_deferred": 5, "stage_queue_revision": 4},
        )
        self.assertEqual(
            summary["results"][1]["lifecycle_bottleneck_deltas"]["metrics"],
            {"stage_replace_deferred": 3.0, "stage_queue_revision": -1.0},
        )
        self.assertEqual(
            summary["results"][1]["lifecycle_bottleneck_deltas"]["deferred_replacement_decision_counts"],
            {"unconfirmed": 3.0},
        )
        self.assertEqual(
            summary["results"][1]["lifecycle_bottleneck_deltas"]["quality_block_reason_counts"],
            {"no_end_marker": -3.0},
        )
        self.assertEqual(
            summary["results"][1]["lifecycle_bottleneck_deltas"]["by_language"]["ko"],
            {"underfinal_count": 1.0, "pending_residue_count": -2.0},
        )
        self.assertEqual(
            summary["results"][1]["evidence_strata_summary"]["lifecycle_without_input_review"]["case_count"],
            10,
        )
        self.assertAlmostEqual(
            summary["results"][1]["evidence_strata_deltas"]["lifecycle_without_input_review"]["final_f1_avg"],
            0.1,
        )
        self.assertAlmostEqual(
            summary["results"][1]["evidence_strata_deltas"]["lifecycle_without_input_review"]["final_boundary_f1_avg"],
            -0.02,
        )
        self.assertEqual(
            summary["results"][1]["evidence_strata_deltas"]["lifecycle_without_input_review"]["staged_residue_count"],
            -1.0,
        )
        self.assertEqual(
            summary["results"][1]["staged_queue_residue_summary"]["queue_residue_total"],
            9,
        )
        self.assertEqual(
            summary["results"][1]["staged_queue_residue_deltas"]["queue_residue_total"],
            1.0,
        )
        self.assertEqual(
            summary["results"][1]["staged_queue_residue_deltas"]["queue_residue_max"],
            2.0,
        )
        self.assertEqual(
            summary["results"][1]["queue_residue_strata_summary"]["queue_len_ge_5"]["case_count"],
            1,
        )
        self.assertEqual(
            summary["results"][1]["queue_residue_strata_deltas"]["no_queue"]["case_count"],
            1.0,
        )
        self.assertEqual(
            summary["results"][1]["queue_residue_strata_deltas"]["queue_len_ge_5"]["metrics"]["stage_queue_revision"],
            6.0,
        )
        self.assertEqual(
            summary["results"][1]["case_exemplar_summary"]["lifecycle_focus_top"][0]["id"],
            "override-heavy",
        )
        self.assertEqual(summary["adoption_review_counts"], {"review-risk": 1})
        self.assertEqual(
            summary["interpretation_flag_counts"],
            {
                "key-tag-precision-regression": 1,
                "language-final-f1-regression": 1,
                "language-precision-regression": 1,
                "overall-final-f1-up-boundary-down": 1,
                "overall-final-f1-up-precision-down": 1,
            },
        )
        self.assertNotIn("topic-only", summary["results"][1]["key_tag_deltas"])

    def test_build_evidence_protocol_marks_challenge_limitations(self) -> None:
        protocol = build_evidence_protocol(
            case_summary={"corpus_role": "challenge-replay"},
            corpus_roles=["challenge-replay"],
            paper_evidence=True,
        )

        self.assertTrue(protocol["paper_evidence"])
        self.assertTrue(protocol["paper_evidence_corpus_eligible"])
        self.assertTrue(protocol["paper_evidence_eligible"])
        self.assertEqual(protocol["corpus_role"], "challenge-replay")
        self.assertEqual(protocol["experiment_stage"], "challenge-replay")
        self.assertIn("failure reproduction", protocol["experiment_stage_description"])
        self.assertEqual(protocol["evidence_use"], "failure replay lifecycle trade-off analysis")
        self.assertEqual(protocol["claim_scope_key"], "failure-lifecycle-tradeoff")
        self.assertEqual(protocol["claim_scope"], "failure-mode lifecycle trade-off only")
        self.assertIn("revision lifecycle trade-off on observed failure cases", protocol["supported_claims"])
        self.assertIn("operating-average quality", protocol["unsupported_claims"])
        self.assertIn("translation-side churn reduction", protocol["deferred_claims"])
        self.assertIn("not an operating-average quality estimate", protocol["limitations"])
        self.assertIn("representative operating corpus", protocol["required_followup"])
        self.assertIn("evidence_protocol.experiment_stage", protocol["required_evidence_fields"])
        self.assertIn("evidence_protocol.claim_scope_key", protocol["required_evidence_fields"])
        self.assertIn("evidence_protocol.supported_claims", protocol["required_evidence_fields"])
        self.assertIn("evidence_protocol.unsupported_claims", protocol["required_evidence_fields"])
        self.assertIn("evidence_protocol.deferred_claims", protocol["required_evidence_fields"])
        self.assertIn("runtime_contract.device", protocol["required_evidence_fields"])
        self.assertIn("lifecycle_replay_contract.state_machine_parity", protocol["required_evidence_fields"])
        self.assertIn("lifecycle_replay_contract.shared_decision_helpers", protocol["required_evidence_fields"])
        self.assertIn("lifecycle_replay_contract.replayed_runtime_signals", protocol["required_evidence_fields"])
        self.assertIn("lifecycle_replay_contract.missing_runtime_signals", protocol["required_evidence_fields"])
        self.assertIn("evidence_summary.results", protocol["required_evidence_fields"])
        self.assertIn("evidence_summary.adoption_review_counts", protocol["required_evidence_fields"])

    def test_build_evidence_protocol_marks_representative_limitations(self) -> None:
        protocol = build_evidence_protocol(
            case_summary={"corpus_role": "representative"},
            corpus_roles=["representative"],
            paper_evidence=True,
        )

        self.assertTrue(protocol["paper_evidence"])
        self.assertTrue(protocol["paper_evidence_corpus_eligible"])
        self.assertTrue(protocol["paper_evidence_eligible"])
        self.assertEqual(protocol["corpus_role"], "representative")
        self.assertEqual(protocol["experiment_stage"], "representative-replay")
        self.assertIn("time/session sample", protocol["experiment_stage_description"])
        self.assertEqual(protocol["evidence_use"], "operating-average estimate")
        self.assertEqual(protocol["claim_scope_key"], "operating-average-finalization")
        self.assertEqual(protocol["claim_scope"], "operating-average finalization estimate only")
        self.assertIn("operating-average finalization estimate for the sampled population", protocol["supported_claims"])
        self.assertIn("failure-mode regression coverage", protocol["unsupported_claims"])
        self.assertIn("translation-side churn reduction", protocol["deferred_claims"])
        self.assertIn("not a failure-mode regression corpus", protocol["limitations"])
        self.assertIn("challenge replay regression check", protocol["required_followup"])
        self.assertIn("case_summary.expected_final_case_count", protocol["required_evidence_fields"])
        self.assertIn(
            "case_summary.representative_metadata.sampling_unit_counts",
            protocol["required_evidence_fields"],
        )
        self.assertIn(
            "case_summary.representative_metadata.sampling_rule_counts",
            protocol["required_evidence_fields"],
        )
        self.assertIn(
            "case_summary.representative_metadata.source_log_count",
            protocol["required_evidence_fields"],
        )
        self.assertIn(
            "case_summary.representative_metadata.review_packet_count",
            protocol["required_evidence_fields"],
        )
        self.assertIn(
            "case_summary.representative_metadata.expected_final_reviewer_counts",
            protocol["required_evidence_fields"],
        )
        self.assertIn(
            "case_summary.representative_review_packet_validation.packet_count",
            protocol["required_evidence_fields"],
        )
        self.assertIn(
            "case_summary.representative_review_packet_validation.ready_packet_count",
            protocol["required_evidence_fields"],
        )
        self.assertIn(
            "case_summary.representative_review_packet_validation.matched_case_count",
            protocol["required_evidence_fields"],
        )

    def test_missing_required_evidence_fields_reports_representative_metadata_absence(self) -> None:
        protocol = build_evidence_protocol(
            case_summary={"corpus_role": "representative"},
            corpus_roles=["representative"],
            paper_evidence=True,
        )
        payload = {
            "evidence_protocol": protocol,
            "runtime_contract": {
                "backend": "sat",
                "device": "cuda",
                "compute_type": "float16",
                "model_source": "local-cache-only",
            },
            "lifecycle_replay_contract": lifecycle_replay_contract(),
            "case_summary": {"corpus_role": "representative", "expected_final_case_count": 5},
            "parameter_axes": ["SENTENCE_CONFIRM_CHUNKS"],
            "evidence_summary": {"results": [], "adoption_review_counts": {}},
        }

        self.assertEqual(
            missing_required_evidence_fields(payload),
            [
                "case_summary.representative_metadata.sampling_unit_counts",
                "case_summary.representative_metadata.sampling_rule_counts",
                "case_summary.representative_metadata.source_log_count",
                "case_summary.representative_metadata.review_packet_count",
                "case_summary.representative_metadata.expected_final_reviewer_counts",
                "case_summary.representative_review_packet_validation.packet_count",
                "case_summary.representative_review_packet_validation.ready_packet_count",
                "case_summary.representative_review_packet_validation.matched_case_count",
            ],
        )

    def test_build_evidence_protocol_marks_exploratory_as_not_paper_evidence(self) -> None:
        protocol = build_evidence_protocol(
            case_summary={"corpus_role": "exploratory"},
            corpus_roles=["exploratory"],
            paper_evidence=False,
        )

        self.assertFalse(protocol["paper_evidence_eligible"])
        self.assertFalse(protocol["paper_evidence_corpus_eligible"])
        self.assertEqual(protocol["experiment_stage"], "exploratory")
        self.assertIn("ad-hoc analysis", protocol["experiment_stage_description"])
        self.assertEqual(protocol["evidence_use"], "ad-hoc exploration")
        self.assertEqual(protocol["claim_scope_key"], "no-paper-claim")
        self.assertEqual(protocol["claim_scope"], "no paper claim")
        self.assertIn("exploratory debugging only", protocol["supported_claims"])
        self.assertIn("paper evidence", protocol["unsupported_claims"])
        self.assertIn("not paper evidence", protocol["limitations"])

    def test_missing_required_evidence_fields_reports_absent_context(self) -> None:
        payload = {
            "evidence_protocol": {
                "paper_evidence": False,
                "paper_evidence_eligible": False,
                "corpus_role": "challenge-replay",
                "claim_scope_key": "failure-lifecycle-tradeoff",
                "required_evidence_fields": [
                    "evidence_protocol.paper_evidence",
                    "evidence_protocol.paper_evidence_eligible",
                    "evidence_protocol.corpus_role",
                    "evidence_protocol.claim_scope_key",
                    "evidence_protocol.supported_claims",
                    "evidence_protocol.unsupported_claims",
                    "evidence_protocol.deferred_claims",
                    "runtime_contract.device",
                    "case_summary.expected_final_case_count",
                    "parameter_axes",
                    "evidence_summary.results",
                    "evidence_summary.adoption_review_counts",
                ],
            },
            "runtime_contract": {"device": "cuda"},
            "case_summary": {"expected_final_case_count": 1109},
            "parameter_axes": ["SENTENCE_CONFIRM_CHUNKS"],
        }

        self.assertEqual(
            missing_required_evidence_fields(payload),
            [
                "evidence_protocol.supported_claims",
                "evidence_protocol.unsupported_claims",
                "evidence_protocol.deferred_claims",
                "evidence_summary.results",
                "evidence_summary.adoption_review_counts",
            ],
        )

    def test_validate_evidence_report_uses_current_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "old-summary.json"
            payload = {
                "evidence_protocol": {
                    "paper_evidence": True,
                    "paper_evidence_eligible": True,
                    "corpus_role": "challenge-replay",
                    "experiment_stage": "challenge-replay",
                    "claim_scope_key": "failure-lifecycle-tradeoff",
                    "required_evidence_fields": [
                        "evidence_protocol.paper_evidence",
                        "evidence_protocol.paper_evidence_eligible",
                        "evidence_protocol.corpus_role",
                        "evidence_protocol.claim_scope_key",
                        "runtime_contract.device",
                        "case_summary.expected_final_case_count",
                        "parameter_axes",
                        "evidence_summary.results",
                        "evidence_summary.adoption_review_counts",
                    ],
                },
                "runtime_contract": {
                    "backend": "sat",
                    "device": "cuda",
                    "compute_type": "float16",
                    "model_source": "local-cache-only",
                },
                "lifecycle_replay_contract": lifecycle_replay_contract(),
                "case_summary": {"corpus_role": "challenge-replay", "expected_final_case_count": 1109},
                "parameter_axes": ["SENTENCE_CONFIRM_CHUNKS"],
                "evidence_summary": {"results": [], "adoption_review_counts": {}},
            }
            path.write_text(json.dumps(payload), encoding="utf-8")

            summary = validate_report(path)

        self.assertEqual(
            summary["missing_required_evidence_fields"],
            [
                "evidence_protocol.supported_claims",
                "evidence_protocol.unsupported_claims",
                "evidence_protocol.deferred_claims",
            ],
        )
        self.assertEqual(summary["parameter_axes"], ["SENTENCE_CONFIRM_CHUNKS"])
        self.assertEqual(summary["job_count"], 0)

    def test_validate_evidence_reports_succeeds_for_current_claim_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "summary.json"
            payload = {
                "evidence_protocol": {
                    "paper_evidence": True,
                    "paper_evidence_eligible": True,
                    "corpus_role": "challenge-replay",
                    "experiment_stage": "challenge-replay",
                    "claim_scope_key": "failure-lifecycle-tradeoff",
                    "supported_claims": ["revision lifecycle trade-off on observed failure cases"],
                    "unsupported_claims": ["operating-average quality"],
                    "deferred_claims": ["translation-side churn reduction"],
                },
                "runtime_contract": {
                    "backend": "sat",
                    "device": "cuda",
                    "compute_type": "float16",
                    "model_source": "local-cache-only",
                },
                "lifecycle_replay_contract": lifecycle_replay_contract(),
                "case_summary": {"corpus_role": "challenge-replay", "expected_final_case_count": 1109},
                "parameter_axes": ["SENTENCE_CONFIRM_CHUNKS"],
                "evidence_summary": {"results": [], "adoption_review_counts": {}},
            }
            path.write_text(json.dumps(payload), encoding="utf-8")

            summary = validate_reports([path])

        self.assertEqual(summary["missing_report_count"], 0)
        self.assertEqual(summary["complete_report_count"], 1)
        self.assertEqual(summary["paper_evidence_complete_report_count"], 1)
        self.assertEqual(summary["paper_evidence_rerun_candidate_count"], 0)
        self.assertEqual(summary["missing_field_counts"], {})
        self.assertEqual(summary["complete_reports"][0]["path"], str(path))
        self.assertEqual(summary["complete_reports"][0]["experiment_stage"], "challenge-replay")
        self.assertEqual(summary["complete_reports"][0]["claim_scope_key"], "failure-lifecycle-tradeoff")
        self.assertEqual(summary["complete_reports"][0]["claim_scope"], "failure-mode lifecycle trade-off only")
        self.assertEqual(summary["experiment_stage_counts"], {"challenge-replay": 1})
        self.assertFalse(summary["mixed_experiment_stage"])
        self.assertEqual(summary["claim_scope_key_counts"], {"failure-lifecycle-tradeoff": 1})
        self.assertFalse(summary["mixed_claim_scope_key"])
        self.assertEqual(summary["complete_experiment_stage_counts"], {"challenge-replay": 1})
        self.assertFalse(summary["complete_mixed_experiment_stage"])
        self.assertEqual(summary["complete_claim_scope_key_counts"], {"failure-lifecycle-tradeoff": 1})
        self.assertFalse(summary["complete_mixed_claim_scope_key"])
        self.assertTrue(summary["complete_reports"][0]["paper_evidence"])

    def test_validate_evidence_reports_counts_missing_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "old-summary.json"
            payload = {
                "evidence_protocol": {
                    "paper_evidence": True,
                    "paper_evidence_eligible": True,
                    "corpus_role": "challenge-replay",
                    "claim_scope_key": "failure-lifecycle-tradeoff",
                },
                "runtime_contract": {
                    "backend": "sat",
                    "device": "cuda",
                    "compute_type": "float16",
                    "model_source": "local-cache-only",
                },
                "lifecycle_replay_contract": lifecycle_replay_contract(),
                "case_summary": {"corpus_role": "challenge-replay", "expected_final_case_count": 1109},
                "parameter_axes": ["SENTENCE_CONFIRM_CHUNKS"],
                "jobs": [
                    {"label": "baseline", "env_overrides": {}},
                    {
                        "label": "sentence_confirm_chunks-1",
                        "env_overrides": {"AVC_DICTATION_SENTENCE_CONFIRM_CHUNKS": "1"},
                    },
                ],
                "evidence_summary": {"results": [], "adoption_review_counts": {}},
            }
            path.write_text(json.dumps(payload), encoding="utf-8")

            summary = validate_reports([path])

        self.assertEqual(summary["missing_report_count"], 1)
        self.assertEqual(summary["complete_report_count"], 0)
        self.assertEqual(summary["paper_evidence_complete_report_count"], 0)
        self.assertEqual(summary["paper_evidence_rerun_candidate_count"], 1)
        self.assertEqual(summary["experiment_stage_counts"], {"challenge-replay": 1})
        self.assertFalse(summary["mixed_experiment_stage"])
        self.assertEqual(summary["claim_scope_key_counts"], {"failure-lifecycle-tradeoff": 1})
        self.assertFalse(summary["mixed_claim_scope_key"])
        self.assertEqual(summary["complete_experiment_stage_counts"], {})
        self.assertFalse(summary["complete_mixed_experiment_stage"])
        self.assertEqual(summary["complete_claim_scope_key_counts"], {})
        self.assertFalse(summary["complete_mixed_claim_scope_key"])
        self.assertEqual(summary["paper_evidence_rerun_candidates"][0]["parameter_axes"], ["SENTENCE_CONFIRM_CHUNKS"])
        self.assertEqual(
            summary["paper_evidence_rerun_candidates"][0]["job_env_overrides"],
            [{}, {"AVC_DICTATION_SENTENCE_CONFIRM_CHUNKS": "1"}],
        )
        self.assertEqual(
            summary["missing_field_counts"],
            {
                "evidence_protocol.experiment_stage": 1,
                "evidence_protocol.deferred_claims": 1,
                "evidence_protocol.supported_claims": 1,
                "evidence_protocol.unsupported_claims": 1,
            },
        )

    def test_expand_evidence_report_paths_collects_only_summary_files_from_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            summary_a = root / "axis-a" / "summary.json"
            summary_refreshed = root / "axis-a" / "summary.refreshed.json"
            summary_b = root / "axis-b" / "nested" / "summary.json"
            raw_job = root / "axis-a" / "baseline.json"
            explicit = root / "explicit-report.json"
            summary_a.parent.mkdir(parents=True)
            summary_b.parent.mkdir(parents=True)
            raw_job.write_text("{}", encoding="utf-8")
            summary_a.write_text("{}", encoding="utf-8")
            summary_refreshed.write_text("{}", encoding="utf-8")
            summary_b.write_text("{}", encoding="utf-8")
            explicit.write_text("{}", encoding="utf-8")

            paths = expand_report_paths([root, explicit])

        self.assertEqual(paths, [summary_a, summary_refreshed, summary_b, explicit])

    def test_refresh_summary_payload_rebuilds_current_evidence_context_from_saved_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            baseline = root / "baseline.json"
            override = root / "sentence_confirm_chunks-1.json"
            for path, final_f1 in ((baseline, 0.5), (override, 0.6)):
                path.write_text(
                    json.dumps(
                        {
                            "case_count": 2,
                            "corpus_role": "challenge-replay",
                            "summary": {
                                "final_precision_avg": 0.8,
                                "final_recall_avg": 0.4,
                                "final_f1_avg": final_f1,
                                "final_boundary_f1_avg": 0.2,
                            },
                            "language_summary": {},
                            "tag_summary": {},
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
            old_summary = root / "summary.json"
            old_summary.write_text(
                json.dumps(
                    {
                        "case_summary": {
                            "case_count": 2,
                            "corpus_role": "challenge-replay",
                            "expected_final_case_count": 2,
                            "draft_count": 0,
                        },
                        "jobs": [
                            {
                                "label": "baseline",
                                "output": str(baseline),
                                "command": "python benchmark.py",
                                "env_overrides": {},
                            },
                            {
                                "label": "sentence_confirm_chunks-1",
                                "output": str(override),
                                "command": "python benchmark.py",
                                "env_overrides": {"AVC_DICTATION_SENTENCE_CONFIRM_CHUNKS": "1"},
                            },
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            payload = refresh_summary_payload(old_summary, paper_evidence=True)

        protocol = payload["evidence_protocol"]
        self.assertTrue(protocol["paper_evidence"])
        self.assertTrue(protocol["paper_evidence_eligible"])
        self.assertEqual(protocol["missing_required_evidence_fields"], [])
        self.assertEqual(payload["parameter_axes"], ["SENTENCE_CONFIRM_CHUNKS"])
        self.assertAlmostEqual(payload["results"][1]["metric_deltas"]["final_f1_avg"], 0.1)

    def test_refresh_summary_path_helpers_collect_summary_files_and_write_refreshed_sibling(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            summary = root / "axis" / "summary.json"
            raw_job = root / "axis" / "baseline.json"
            summary.parent.mkdir(parents=True)
            summary.write_text("{}", encoding="utf-8")
            raw_job.write_text("{}", encoding="utf-8")

            paths = expand_refresh_summary_paths([root])

        self.assertEqual(paths, [summary])
        self.assertEqual(_default_refreshed_summary_path(summary), summary.with_name("summary.refreshed.json"))

    def test_refresh_summary_cli_can_skip_missing_job_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            summary = root / "dry-run" / "summary.json"
            summary.parent.mkdir(parents=True)
            summary.write_text(
                json.dumps(
                    {
                        "jobs": [
                            {
                                "label": "baseline",
                                "output": str(root / "dry-run" / "missing-baseline.json"),
                                "command": "python benchmark.py",
                                "env_overrides": {},
                            }
                        ],
                        "case_summary": {"corpus_role": "challenge-replay"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            stdout = StringIO()

            with patch("sys.argv", ["refresh", str(root), "--skip-missing"]), patch("sys.stdout", stdout):
                exit_code = refresh_summary_main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["refreshed_count"], 0)
        self.assertEqual(payload["skipped_count"], 1)
        self.assertIn("missing job output files", payload["skipped"][0]["reason"])

    def test_summarize_complete_evidence_reports_extracts_axis_deltas(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "summary.refreshed.json"
            payload = {
                "evidence_protocol": {
                    "paper_evidence": True,
                    "paper_evidence_eligible": True,
                    "corpus_role": "challenge-replay",
                    "experiment_stage": "challenge-replay",
                    "claim_scope_key": "failure-lifecycle-tradeoff",
                    "supported_claims": ["revision lifecycle trade-off on observed failure cases"],
                    "unsupported_claims": ["operating-average quality"],
                    "deferred_claims": ["translation-side churn reduction"],
                },
                "runtime_contract": {
                    "backend": "sat",
                    "device": "cuda",
                    "compute_type": "float16",
                    "model_source": "local-cache-only",
                },
                "lifecycle_replay_contract": lifecycle_replay_contract(),
                "case_summary": {"corpus_role": "challenge-replay", "expected_final_case_count": 1109},
                "parameter_axes": ["SENTENCE_CONFIRM_CHUNKS"],
                "evidence_summary": {
                    "adoption_review_counts": {"review-risk": 1},
                    "results": [
                        {
                            "label": "baseline",
                            "metrics": {
                                "final_precision_avg": 0.6019205720812749,
                                "final_recall_avg": 0.43994445181910236,
                                "final_f1_avg": 0.48324216347151316,
                                "final_boundary_f1_avg": 0.10774902104020108,
                                "finalized_per_stage_start": 0.7115998581057112,
                            },
                        },
                        {
                            "label": "sentence_confirm_chunks-1",
                            "env_overrides": {"AVC_DICTATION_SENTENCE_CONFIRM_CHUNKS": "1"},
                            "adoption_review": "review-risk",
                            "interpretation_flags": ["language-precision-regression"],
                            "metric_deltas": {
                                "final_f1_avg": 0.01,
                                "final_precision_avg": -0.02,
                                "final_recall_avg": 0.03,
                                "final_boundary_f1_avg": -0.04,
                            },
                            "lifecycle_bottleneck_deltas": {
                                "metrics": {
                                    "stage_replace_deferred": -2.0,
                                    "stage_queue_revision": -3.0,
                                }
                            },
                            "staged_queue_residue_deltas": {
                                "queue_residue_total": -4.0,
                                "queue_residue_max": -1.0,
                            },
                            "evidence_strata_deltas": {
                                "lifecycle_without_input_review": {
                                    "final_boundary_f1_avg": 0.05,
                                }
                            },
                        },
                    ],
                },
            }
            path.write_text(json.dumps(payload), encoding="utf-8")

            summary = summarize_reports([path])
            markdown = render_evidence_markdown(summary)

        self.assertEqual(summary["report_count"], 1)
        self.assertEqual(summary["unique_axis_count"], 1)
        self.assertEqual(summary["candidate_count"], 1)
        self.assertEqual(summary["unique_axis_candidate_count"], 1)
        self.assertEqual(summary["experiment_stage_counts"], {"challenge-replay": 1})
        self.assertFalse(summary["mixed_experiment_stage"])
        self.assertEqual(summary["claim_scope_key_counts"], {"failure-lifecycle-tradeoff": 1})
        self.assertFalse(summary["mixed_claim_scope_key"])
        self.assertEqual(summary["axis_name_counts"], {"SENTENCE_CONFIRM_CHUNKS": 1})
        self.assertEqual(summary["duplicate_axis_counts"], {})
        self.assertEqual(summary["adoption_review_counts"], {"review-risk": 1})
        self.assertEqual(summary["unique_axis_adoption_review_counts"], {"review-risk": 1})
        self.assertEqual(summary["axis_conclusion_counts"], {"tradeoff-gain": 1})
        self.assertEqual(summary["hypothesis_status_counts"], {"축소": 1})
        self.assertEqual(
            summary["lifecycle_replay_summary"]["state_machine_parity_counts"],
            {"partial": 1},
        )
        self.assertEqual(
            summary["lifecycle_replay_summary"]["runtime_state_owner_counts"],
            {
                "src.app.dictation_node_sentence_candidate_commit_buffer."
                "SentenceCandidateCommitBufferNode": 1
            },
        )
        self.assertEqual(
            summary["lifecycle_replay_summary"]["replay_state_owner_counts"],
            {"tests.eval.dictation_ai.sbd_benchmark.LifecycleState": 1},
        )
        self.assertEqual(
            summary["lifecycle_replay_summary"]["missing_runtime_signal_counts"][
                "translation request/output linkage"
            ],
            1,
        )
        self.assertEqual(
            summary["axis_conclusion_descriptions"]["tradeoff-gain"],
            "At least one candidate improves final F1, but review-risk flags mean the gain has precision, language, tag, or boundary trade-offs.",
        )
        self.assertEqual(
            summary["hypothesis_status_descriptions"]["축소"],
            "The axis has useful signal, but trade-offs require narrowing the claim to a failure-mode or condition.",
        )
        self.assertEqual(
            summary["baseline_metric_summary"]["final_f1_avg"],
            {
                "report_count": 1,
                "consistent": True,
                "value": 0.483242163472,
                "unique_values": [0.483242163472],
            },
        )
        self.assertEqual(
            summary["baseline_metric_summary"]["final_boundary_f1_avg"]["value"],
            0.10774902104,
        )
        self.assertNotIn("representative_reports", summary)
        self.assertEqual(summary["axis_representative_reports"][0]["axis"], "SENTENCE_CONFIRM_CHUNKS")
        self.assertEqual(summary["axis_representative_reports"][0]["conclusion"], "tradeoff-gain")
        self.assertEqual(summary["axis_representative_reports"][0]["hypothesis_status"], "축소")
        claim_statuses = {
            claim["claim_id"]: claim["status"] for claim in summary["paper_claim_matrix"]
        }
        claim_evidence = {
            claim["claim_id"]: claim["evidence"] for claim in summary["paper_claim_matrix"]
        }
        self.assertEqual(claim_statuses["partial_final_separation"], "사용 가능")
        self.assertEqual(claim_statuses["layered_finalization_metrics"], "사용 가능")
        self.assertEqual(claim_statuses["threshold_optimization_limit"], "사용 가능")
        self.assertEqual(
            claim_evidence["threshold_optimization_limit"],
            "hypothesis_status_counts classify parameter axes as kept baseline, narrowed, or discarded",
        )
        self.assertEqual(claim_statuses["challenge_replay_baseline"], "사용 가능")
        self.assertEqual(claim_statuses["operating_average_quality"], "사용 금지")
        self.assertEqual(claim_statuses["translation_stability"], "보류")
        self.assertEqual(claim_statuses["raw_stt_accuracy"], "사용 금지")
        self.assertEqual(claim_statuses["runtime_loop_equivalence"], "사용 금지")
        self.assertIn("state_machine_parity_counts={'partial': 1}", claim_evidence["runtime_loop_equivalence"])
        self.assertIn(
            "translation request/output linkage",
            claim_evidence["runtime_loop_equivalence"],
        )
        self.assertEqual(summary["reports"][0]["experiment_stage"], "challenge-replay")
        self.assertEqual(summary["reports"][0]["claim_scope_key"], "failure-lifecycle-tradeoff")
        self.assertEqual(summary["reports"][0]["claim_scope"], "failure-mode lifecycle trade-off only")
        self.assertEqual(summary["reports"][0]["parameter_axes"], ["SENTENCE_CONFIRM_CHUNKS"])
        self.assertEqual(
            summary["reports"][0]["candidates"][0]["stage_replace_deferred_delta"],
            -2.0,
        )
        self.assertEqual(
            summary["reports"][0]["candidates"][0]["stage_queue_revision_delta"],
            -3.0,
        )
        self.assertEqual(
            summary["reports"][0]["candidates"][0]["queue_residue_total_delta"],
            -4.0,
        )
        self.assertEqual(
            summary["reports"][0]["candidates"][0]["queue_residue_max_delta"],
            -1.0,
        )
        self.assertEqual(
            summary["reports"][0]["candidates"][0]["clean_lifecycle_boundary_f1_delta"],
            0.05,
        )
        self.assertIn(
            "| challenge-replay | SENTENCE_CONFIRM_CHUNKS | sentence_confirm_chunks-1 | +0.0100 | -0.0200 | +0.0300 | -0.0400 | -2.0000 | -3.0000 | -4.0000 | -1.0000 | +0.0500 | review-risk | language-precision-regression |",
            markdown,
        )
        self.assertIn("experiment_stage_counts: challenge-replay=1", markdown)
        self.assertIn("mixed_experiment_stage: false", markdown)
        self.assertIn("claim_scope_key_counts: failure-lifecycle-tradeoff=1", markdown)
        self.assertIn("mixed_claim_scope_key: false", markdown)
        self.assertIn("duplicate_axis_counts: ", markdown)
        self.assertIn("unique_axis_adoption_review_counts: review-risk=1", markdown)
        self.assertIn("axis_conclusion_counts: tradeoff-gain=1", markdown)
        self.assertIn("hypothesis_status_counts: 축소=1", markdown)
        self.assertIn("baseline_metric_summary: final_precision_avg=0.601920572081", markdown)
        self.assertIn("lifecycle_state_machine_parity_counts: partial=1", markdown)
        self.assertIn(
            "lifecycle_runtime_state_owner_counts: "
            "src.app.dictation_node_sentence_candidate_commit_buffer."
            "SentenceCandidateCommitBufferNode=1",
            markdown,
        )
        self.assertIn(
            "lifecycle_replay_state_owner_counts: "
            "tests.eval.dictation_ai.sbd_benchmark.LifecycleState=1",
            markdown,
        )
        self.assertIn("translation request/output linkage=1", markdown)
        self.assertIn("## Axis Conclusion Legend", markdown)
        self.assertIn(
            "| tradeoff-gain | At least one candidate improves final F1, but review-risk flags mean the gain has precision, language, tag, or boundary trade-offs. |",
            markdown,
        )
        self.assertIn("## Hypothesis Status Legend", markdown)
        self.assertIn(
            "| 축소 | The axis has useful signal, but trade-offs require narrowing the claim to a failure-mode or condition. |",
            markdown,
        )
        self.assertIn("## Baseline Metric Summary", markdown)
        self.assertIn("| final_f1_avg | true | 1 | 0.483242163472 | 0.483242163472 |", markdown)
        self.assertIn("## Paper Claim Matrix", markdown)
        self.assertIn(
            "| operating_average_quality | Operating-average quality improved. | 사용 금지 | no representative replay evidence in this package | human-reviewed representative cases and validator summary |",
            markdown,
        )
        self.assertIn(
            "| translation_stability | The final-only sink improved downstream translation stability. | 보류 | no translation replay evidence in this package | final event, translation request id, and translation output replay |",
            markdown,
        )
        self.assertIn(
            "| runtime_loop_equivalence | Text replay is equivalent to the full runtime loop. | 사용 금지 | state_machine_parity_counts={'partial': 1}; missing_runtime_signal_counts=",
            markdown,
        )
        self.assertIn("## Representative Axis Reports", markdown)
        self.assertIn(
            f"| SENTENCE_CONFIRM_CHUNKS | {path} | 1 | 5,1,0 | tradeoff-gain | 축소 |",
            markdown,
        )
        self.assertIn("## Candidate Deltas", markdown)

    def test_summarize_complete_evidence_prefers_richer_duplicate_axis_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            simple_path = Path(tmpdir) / "simple.json"
            rich_path = Path(tmpdir) / "rich.json"
            base_payload = {
                "evidence_protocol": {
                    "paper_evidence": True,
                    "paper_evidence_eligible": True,
                    "corpus_role": "challenge-replay",
                    "experiment_stage": "challenge-replay",
                    "claim_scope_key": "failure-lifecycle-tradeoff",
                    "supported_claims": ["revision lifecycle trade-off on observed failure cases"],
                    "unsupported_claims": ["operating-average quality"],
                    "deferred_claims": ["translation-side churn reduction"],
                },
                "runtime_contract": {
                    "backend": "sat",
                    "device": "cuda",
                    "compute_type": "float16",
                    "model_source": "local-cache-only",
                },
                "lifecycle_replay_contract": lifecycle_replay_contract(),
                "case_summary": {"corpus_role": "challenge-replay", "expected_final_case_count": 1109},
                "parameter_axes": ["SHORT_NO_END_FRAGMENT_UNITS"],
            }
            simple_payload = dict(base_payload)
            simple_payload["evidence_summary"] = {
                "adoption_review_counts": {"review-risk": 1},
                "results": [
                    {"label": "baseline"},
                    {
                        "label": "short_no_end_fragment_units-3",
                        "adoption_review": "review-risk",
                        "metric_deltas": {"final_f1_avg": -0.01},
                    },
                ],
            }
            rich_payload = dict(base_payload)
            rich_payload["evidence_summary"] = {
                "adoption_review_counts": {"review-risk": 1},
                "results": [
                    {"label": "baseline"},
                    {
                        "label": "short_no_end_fragment_units-3",
                        "adoption_review": "review-risk",
                        "metric_deltas": {"final_f1_avg": -0.01},
                        "lifecycle_bottleneck_deltas": {
                            "metrics": {
                                "stage_replace_deferred": 404.0,
                                "stage_queue_revision": 198.0,
                            }
                        },
                    },
                ],
            }
            simple_path.write_text(json.dumps(simple_payload), encoding="utf-8")
            rich_path.write_text(json.dumps(rich_payload), encoding="utf-8")

            summary = summarize_reports([simple_path, rich_path])

        self.assertEqual(summary["report_count"], 2)
        self.assertEqual(summary["unique_axis_count"], 1)
        self.assertEqual(summary["candidate_count"], 2)
        self.assertEqual(summary["unique_axis_candidate_count"], 1)
        self.assertEqual(summary["duplicate_axis_counts"], {"SHORT_NO_END_FRAGMENT_UNITS": 2})
        self.assertEqual(summary["adoption_review_counts"], {"review-risk": 2})
        self.assertEqual(summary["unique_axis_adoption_review_counts"], {"review-risk": 1})
        self.assertEqual(summary["axis_conclusion_counts"], {"baseline-preferred-tradeoff": 1})
        self.assertEqual(summary["hypothesis_status_counts"], {"유지": 1})
        self.assertEqual(summary["axis_representative_reports"][0]["path"], str(rich_path))
        self.assertEqual(summary["axis_representative_reports"][0]["richness_score"][0], 2)
        self.assertEqual(summary["axis_representative_reports"][0]["conclusion"], "baseline-preferred-tradeoff")
        self.assertEqual(summary["axis_representative_reports"][0]["hypothesis_status"], "유지")

    def test_summarize_complete_evidence_classifies_no_effect_axis(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "summary.json"
            payload = {
                "evidence_protocol": {
                    "paper_evidence": True,
                    "paper_evidence_eligible": True,
                    "corpus_role": "challenge-replay",
                    "experiment_stage": "challenge-replay",
                    "claim_scope_key": "failure-lifecycle-tradeoff",
                    "supported_claims": ["revision lifecycle trade-off on observed failure cases"],
                    "unsupported_claims": ["operating-average quality"],
                    "deferred_claims": ["translation-side churn reduction"],
                },
                "runtime_contract": {
                    "backend": "sat",
                    "device": "cuda",
                    "compute_type": "float16",
                    "model_source": "local-cache-only",
                },
                "lifecycle_replay_contract": lifecycle_replay_contract(),
                "case_summary": {"corpus_role": "challenge-replay", "expected_final_case_count": 1109},
                "parameter_axes": ["NO_TEXT_STALE_STAGE_SUPPRESS_CHUNKS"],
                "evidence_summary": {
                    "adoption_review_counts": {"no-risk-flag": 1},
                    "results": [
                        {"label": "baseline"},
                        {
                            "label": "no_text_stale_stage_suppress_chunks-3",
                            "adoption_review": "no-risk-flag",
                            "metric_deltas": {
                                "final_f1_avg": 0.0,
                                "final_precision_avg": 0.0,
                                "final_boundary_f1_avg": 0.0,
                            },
                        },
                    ],
                },
            }
            path.write_text(json.dumps(payload), encoding="utf-8")

            summary = summarize_reports([path])

        self.assertEqual(summary["axis_conclusion_counts"], {"no-effect-or-tiny": 1})
        self.assertEqual(summary["axis_representative_reports"][0]["conclusion"], "no-effect-or-tiny")
        self.assertEqual(summary["hypothesis_status_counts"], {"폐기": 1})
        self.assertEqual(summary["axis_representative_reports"][0]["hypothesis_status"], "폐기")

    def test_summarize_complete_evidence_maps_minor_no_risk_gain_to_keep_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "summary.json"
            payload = {
                "evidence_protocol": {
                    "paper_evidence": True,
                    "paper_evidence_eligible": True,
                    "corpus_role": "challenge-replay",
                    "experiment_stage": "challenge-replay",
                    "claim_scope_key": "failure-lifecycle-tradeoff",
                    "supported_claims": ["revision lifecycle trade-off on observed failure cases"],
                    "unsupported_claims": ["operating-average quality"],
                    "deferred_claims": ["translation-side churn reduction"],
                },
                "runtime_contract": {
                    "backend": "sat",
                    "device": "cuda",
                    "compute_type": "float16",
                    "model_source": "local-cache-only",
                },
                "lifecycle_replay_contract": lifecycle_replay_contract(),
                "case_summary": {"corpus_role": "challenge-replay", "expected_final_case_count": 1109},
                "parameter_axes": ["REVISION_FALLBACK_COVERAGE_MIN"],
                "evidence_summary": {
                    "adoption_review_counts": {"no-risk-flag": 1},
                    "results": [
                        {"label": "baseline"},
                        {
                            "label": "revision_fallback_coverage_min-0.55",
                            "adoption_review": "no-risk-flag",
                            "metric_deltas": {
                                "final_f1_avg": 0.001,
                                "final_precision_avg": 0.0005,
                                "final_boundary_f1_avg": 0.0005,
                            },
                        },
                    ],
                },
            }
            path.write_text(json.dumps(payload), encoding="utf-8")

            summary = summarize_reports([path])

        self.assertEqual(summary["axis_conclusion_counts"], {"minor-no-risk-gain": 1})
        self.assertEqual(summary["hypothesis_status_counts"], {"유지": 1})
        self.assertEqual(summary["axis_representative_reports"][0]["hypothesis_status"], "유지")

    def test_complete_report_paths_filters_incomplete_historical_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            complete_path = Path(tmpdir) / "complete.json"
            incomplete_path = Path(tmpdir) / "incomplete.json"
            base_payload = {
                "evidence_protocol": {
                    "paper_evidence": True,
                    "paper_evidence_eligible": True,
                    "corpus_role": "challenge-replay",
                    "experiment_stage": "challenge-replay",
                    "claim_scope_key": "failure-lifecycle-tradeoff",
                    "supported_claims": ["revision lifecycle trade-off on observed failure cases"],
                    "unsupported_claims": ["operating-average quality"],
                    "deferred_claims": ["translation-side churn reduction"],
                },
                "runtime_contract": {
                    "backend": "sat",
                    "device": "cuda",
                    "compute_type": "float16",
                    "model_source": "local-cache-only",
                },
                "lifecycle_replay_contract": lifecycle_replay_contract(),
                "case_summary": {"corpus_role": "challenge-replay", "expected_final_case_count": 1109},
                "parameter_axes": ["SENTENCE_CONFIRM_CHUNKS"],
            }
            complete_payload = dict(base_payload)
            complete_payload["evidence_summary"] = {"results": [], "adoption_review_counts": {}}
            incomplete_payload = dict(base_payload)
            incomplete_payload["evidence_summary"] = {"results": []}
            complete_path.write_text(json.dumps(complete_payload), encoding="utf-8")
            incomplete_path.write_text(json.dumps(incomplete_payload), encoding="utf-8")

            self.assertEqual(complete_report_paths([incomplete_path, complete_path]), [complete_path])

    def test_render_markdown_summary_includes_metric_and_language_deltas(self) -> None:
        payload = {
            "dry_run": False,
            "corpus_roles": ["challenge-replay"],
            "parameter_axes": ["SENTENCE_CONFIRM_CHUNKS"],
            "runtime_contract": {
                "backend": "sat",
                "device": "cuda",
                "compute_type": "float16",
                "offline_model_env": {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"},
                "model_source": "local-cache-only",
            },
            "lifecycle_replay_contract": lifecycle_replay_contract(),
            "evidence_protocol": {
                "paper_evidence_requested": True,
                "paper_evidence": True,
                "paper_evidence_eligible": True,
                "corpus_role": "challenge-replay",
                "corpus_interpretation": "failure-enriched challenge replay baseline",
                "experiment_stage": "challenge-replay",
                "experiment_stage_description": "failure reproduction and revision lifecycle trade-off analysis",
                "evidence_use": "failure replay lifecycle trade-off analysis",
                "claim_scope_key": "failure-lifecycle-tradeoff",
                "claim_scope": "failure-mode lifecycle trade-off only",
                "supported_claims": [
                    "revision lifecycle trade-off on observed failure cases",
                    "finalization metric decomposition",
                ],
                "unsupported_claims": [
                    "operating-average quality",
                    "raw STT WER/CER improvement",
                ],
                "deferred_claims": [
                    "operating-average finalization quality",
                    "translation-side churn reduction",
                ],
                "required_evidence_fields": [
                    "evidence_protocol.paper_evidence",
                    "evidence_protocol.paper_evidence_eligible",
                    "evidence_protocol.corpus_role",
                    "evidence_protocol.claim_scope_key",
                    "runtime_contract.device",
                    "case_summary.expected_final_case_count",
                    "parameter_axes",
                    "evidence_summary.results",
                    "evidence_summary.adoption_review_counts",
                ],
                "missing_required_evidence_fields": [],
            },
            "case_summary": {
                "corpus_role": "challenge-replay",
                "case_count": 1113,
                "expected_final_case_count": 1109,
                "draft_count": 0,
            },
            "jobs": [{"label": "baseline"}, {"label": "sentence_confirm_chunks-1"}],
            "evidence_summary": {
                "results": [
                    {
                        "label": "baseline",
                        "env_overrides": {},
                        "metric_deltas": {"final_f1_avg": 0.0},
                        "interpretation_flags": [],
                        "key_tag_deltas": {"missing-final": {"final_f1_avg": 0.0}},
                        "lifecycle_bottleneck_summary": {
                            "metrics": {
                                "stage_replace_deferred": 10,
                                "stage_queue_revision": 8,
                                "stage_candidate_quality_blocked": 7,
                            },
                            "quality_block_reason_counts": {
                                "no_end_marker": 5,
                                "short_no_end_fragment": 4,
                            },
                            "deferred_replacement_decision_counts": {
                                "unconfirmed": 8,
                                "open_latin_clause": 2,
                                "unconfirmed_cjk": 1,
                            },
                        },
                        "staged_queue_residue_summary": {
                            "queue_residue_case_count": 6,
                            "queue_residue_total": 12,
                            "queue_residue_avg_when_present": 2.0,
                            "queue_residue_max": 4,
                            "queue_residue_len_ge_2_count": 3,
                            "queue_residue_len_ge_5_count": 0,
                            "active_staged_residue_case_count": 9,
                            "pending_residue_case_count": 8,
                            "top_queue_residue_cases": [
                                {
                                    "id": "baseline-queue-heavy",
                                    "queue_len": 4,
                                    "stage_queue_revision": 8,
                                    "stage_replace_deferred": 10,
                                    "final_f1": 0.2,
                                    "final_boundary_f1": 0.0,
                                    "active_staged": True,
                                    "pending": True,
                                }
                            ],
                        },
                        "staged_queue_residue_deltas": {
                            "queue_residue_case_count": 0.0,
                            "queue_residue_total": 0.0,
                            "queue_residue_avg_when_present": 0.0,
                            "queue_residue_max": 0.0,
                            "queue_residue_len_ge_2_count": 0.0,
                            "queue_residue_len_ge_5_count": 0.0,
                            "active_staged_residue_case_count": 0.0,
                            "pending_residue_case_count": 0.0,
                        },
                        "queue_residue_strata_summary": {
                            "no_queue": {
                                "case_count": 90,
                                "final_f1_avg": 0.6,
                                "final_boundary_f1_avg": 0.3,
                                "staged_residue_count": 5,
                                "empty_final_count": 2,
                                "metrics": {"stage_queue_revision": 1, "stage_replace_deferred": 2},
                            },
                            "queue_len_1": {
                                "case_count": 4,
                                "final_f1_avg": 0.4,
                                "final_boundary_f1_avg": 0.2,
                                "staged_residue_count": 4,
                                "empty_final_count": 1,
                                "metrics": {"stage_queue_revision": 2, "stage_replace_deferred": 3},
                            },
                            "queue_len_2_to_4": {
                                "case_count": 5,
                                "final_f1_avg": 0.3,
                                "final_boundary_f1_avg": 0.1,
                                "staged_residue_count": 5,
                                "empty_final_count": 2,
                                "metrics": {"stage_queue_revision": 4, "stage_replace_deferred": 5},
                            },
                            "queue_len_ge_5": {
                                "case_count": 1,
                                "final_f1_avg": 0.1,
                                "final_boundary_f1_avg": 0.0,
                                "staged_residue_count": 1,
                                "empty_final_count": 1,
                                "metrics": {"stage_queue_revision": 6, "stage_replace_deferred": 7},
                            },
                        },
                        "queue_residue_strata_deltas": {
                            "no_queue": {
                                "final_f1_avg": 0.0,
                                "final_boundary_f1_avg": 0.0,
                                "staged_residue_count": 0.0,
                                "empty_final_count": 0.0,
                                "metrics": {"stage_queue_revision": 0.0, "stage_replace_deferred": 0.0},
                            }
                        },
                        "evidence_strata_summary": {
                            "lifecycle_focus": {"case_count": 100},
                            "lifecycle_without_input_review": {
                                "case_count": 96,
                                "final_f1_avg": 0.45,
                                "final_boundary_f1_avg": 0.20,
                                "staged_residue_count": 12,
                            },
                            "input_contamination_review": {
                                "case_count": 4,
                                "final_f1_avg": 0.8,
                                "final_boundary_f1_avg": 0.5,
                            },
                        },
                        "evidence_strata_deltas": {
                            "lifecycle_without_input_review": {
                                "final_f1_avg": 0.0,
                                "final_boundary_f1_avg": 0.0,
                                "staged_residue_count": 0.0,
                            },
                            "input_contamination_review": {
                                "final_f1_avg": 0.0,
                                "final_boundary_f1_avg": 0.0,
                            },
                        },
                        "case_exemplar_summary": {
                            "lifecycle_focus_top": [
                                {
                                    "id": "baseline-heavy",
                                    "bottleneck_score": 10.0,
                                    "final_f1": 0.2,
                                    "final_boundary_f1": 0.0,
                                    "metrics": {
                                        "stage_queue_revision": 3,
                                        "stage_replace_deferred": 5,
                                        "stage_candidate_quality_blocked": 2,
                                    },
                                }
                            ]
                        },
                    },
                    {
                        "label": "sentence_confirm_chunks-1",
                        "env_overrides": {"AVC_DICTATION_SENTENCE_CONFIRM_CHUNKS": "1"},
                        "metric_deltas": {
                            "final_f1_avg": 0.1,
                            "final_precision_avg": -0.2,
                            "final_recall_avg": 0.3,
                        },
                        "language_deltas": {
                            "ko": {
                                "final_precision_avg": -0.2,
                                "final_f1_avg": -0.1,
                                "staged_residue_count": -2.0,
                                "empty_final_count": 1.0,
                            }
                        },
                        "interpretation_flags": [
                            "overall-final-f1-up-precision-down",
                            "language-final-f1-regression",
                            "language-precision-regression",
                        ],
                        "adoption_review": "review-risk",
                        "key_tag_deltas": {
                            "missing-final": {
                                "final_f1_avg": 0.2,
                                "staged_residue_count": -2.0,
                                "empty_final_count": 1.0,
                            }
                        },
                        "lifecycle_bottleneck_deltas": {
                            "metrics": {
                                "stage_replace_deferred": -3.0,
                                "stage_queue_revision": -1.0,
                                "stage_candidate_quality_blocked": 2.0,
                            },
                            "quality_block_reason_counts": {
                                "no_end_marker": 4.0,
                                "short_no_end_fragment": -2.0,
                            },
                            "deferred_replacement_decision_counts": {
                                "unconfirmed": -5.0,
                                "open_latin_clause": 1.0,
                                "unconfirmed_cjk": 0.0,
                            },
                        },
                        "lifecycle_bottleneck_summary": {
                            "metrics": {
                                "stage_replace_deferred": 7,
                                "stage_queue_revision": 7,
                                "stage_candidate_quality_blocked": 9,
                            },
                            "quality_block_reason_counts": {
                                "no_end_marker": 9,
                                "short_no_end_fragment": 2,
                            },
                            "deferred_replacement_decision_counts": {
                                "unconfirmed": 3,
                                "open_latin_clause": 3,
                                "unconfirmed_cjk": 1,
                            },
                        },
                        "staged_queue_residue_summary": {
                            "queue_residue_case_count": 5,
                            "queue_residue_total": 15,
                            "queue_residue_avg_when_present": 3.0,
                            "queue_residue_max": 6,
                            "queue_residue_len_ge_2_count": 4,
                            "queue_residue_len_ge_5_count": 1,
                            "active_staged_residue_case_count": 7,
                            "pending_residue_case_count": 6,
                            "top_queue_residue_cases": [
                                {
                                    "id": "override-queue-heavy",
                                    "queue_len": 6,
                                    "stage_queue_revision": 7,
                                    "stage_replace_deferred": 7,
                                    "final_f1": 0.3,
                                    "final_boundary_f1": 0.1,
                                    "active_staged": False,
                                    "pending": True,
                                }
                            ],
                        },
                        "staged_queue_residue_deltas": {
                            "queue_residue_case_count": -1.0,
                            "queue_residue_total": 3.0,
                            "queue_residue_avg_when_present": 1.0,
                            "queue_residue_max": 2.0,
                            "queue_residue_len_ge_2_count": 1.0,
                            "queue_residue_len_ge_5_count": 1.0,
                            "active_staged_residue_case_count": -2.0,
                            "pending_residue_case_count": -2.0,
                        },
                        "queue_residue_strata_summary": {
                            "no_queue": {
                                "case_count": 91,
                                "final_f1_avg": 0.7,
                                "final_boundary_f1_avg": 0.4,
                                "staged_residue_count": 4,
                                "empty_final_count": 1,
                                "metrics": {"stage_queue_revision": 1, "stage_replace_deferred": 1},
                            },
                            "queue_len_1": {
                                "case_count": 3,
                                "final_f1_avg": 0.5,
                                "final_boundary_f1_avg": 0.2,
                                "staged_residue_count": 3,
                                "empty_final_count": 1,
                                "metrics": {"stage_queue_revision": 1, "stage_replace_deferred": 2},
                            },
                            "queue_len_2_to_4": {
                                "case_count": 5,
                                "final_f1_avg": 0.35,
                                "final_boundary_f1_avg": 0.1,
                                "staged_residue_count": 5,
                                "empty_final_count": 2,
                                "metrics": {"stage_queue_revision": 3, "stage_replace_deferred": 4},
                            },
                            "queue_len_ge_5": {
                                "case_count": 1,
                                "final_f1_avg": 0.1,
                                "final_boundary_f1_avg": 0.0,
                                "staged_residue_count": 1,
                                "empty_final_count": 1,
                                "metrics": {"stage_queue_revision": 6, "stage_replace_deferred": 7},
                            },
                        },
                        "queue_residue_strata_deltas": {
                            "no_queue": {
                                "final_f1_avg": 0.1,
                                "final_boundary_f1_avg": 0.1,
                                "staged_residue_count": -1.0,
                                "empty_final_count": -1.0,
                                "metrics": {"stage_queue_revision": 0.0, "stage_replace_deferred": -1.0},
                            },
                            "queue_len_ge_5": {
                                "final_f1_avg": 0.0,
                                "final_boundary_f1_avg": 0.0,
                                "staged_residue_count": 0.0,
                                "empty_final_count": 0.0,
                                "metrics": {"stage_queue_revision": 0.0, "stage_replace_deferred": 0.0},
                            },
                        },
                        "evidence_strata_summary": {
                            "lifecycle_focus": {"case_count": 100},
                            "lifecycle_without_input_review": {
                                "case_count": 95,
                                "final_f1_avg": 0.55,
                                "final_boundary_f1_avg": 0.18,
                                "staged_residue_count": 10,
                            },
                            "input_contamination_review": {
                                "case_count": 5,
                                "final_f1_avg": 0.7,
                                "final_boundary_f1_avg": 0.4,
                            },
                        },
                        "evidence_strata_deltas": {
                            "lifecycle_without_input_review": {
                                "final_f1_avg": 0.1,
                                "final_boundary_f1_avg": -0.02,
                                "staged_residue_count": -2.0,
                            },
                            "input_contamination_review": {
                                "final_f1_avg": -0.1,
                                "final_boundary_f1_avg": -0.1,
                            },
                        },
                        "case_exemplar_summary": {
                            "lifecycle_focus_top": [
                                {
                                    "id": "override-heavy",
                                    "bottleneck_score": 11.0,
                                    "final_f1": 0.3,
                                    "final_boundary_f1": 0.1,
                                    "metrics": {
                                        "stage_queue_revision": 4,
                                        "stage_replace_deferred": 6,
                                        "stage_candidate_quality_blocked": 1,
                                    },
                                }
                            ]
                        },
                    },
                ],
                "interpretation_flag_counts": {
                    "overall-final-f1-up-precision-down": 1,
                    "language-final-f1-regression": 1,
                    "language-precision-regression": 1,
                },
                "adoption_review_counts": {"review-risk": 1},
            },
            "results": [
                {
                    "label": "baseline",
                    "env_overrides": {},
                    "metrics": {"final_f1_avg": 0.5},
                    "metric_deltas": {"final_f1_avg": 0.0},
                    "language_summary": {"ko": {"final_f1_avg": 0.5, "staged_residue_count": 3}},
                    "language_deltas": {"ko": {"final_f1_avg": 0.0, "staged_residue_count": 0.0}},
                    "tag_summary": {"missing-final": {"case_count": 3, "final_f1_avg": 0.5}},
                    "tag_deltas": {"missing-final": {"case_count": 0.0, "final_f1_avg": 0.0}},
                },
                {
                    "label": "sentence_confirm_chunks-1",
                    "env_overrides": {"AVC_DICTATION_SENTENCE_CONFIRM_CHUNKS": "1"},
                    "metrics": {"final_f1_avg": 0.6},
                    "metric_deltas": {"final_f1_avg": 0.1},
                    "language_summary": {"ko": {"final_f1_avg": 0.4, "staged_residue_count": 1}},
                    "language_deltas": {"ko": {"final_f1_avg": -0.1, "staged_residue_count": -2.0}},
                    "tag_summary": {"missing-final": {"case_count": 3, "final_f1_avg": 0.7}},
                    "tag_deltas": {"missing-final": {"case_count": 0.0, "final_f1_avg": 0.2}},
                },
            ],
        }

        markdown = render_markdown_summary(payload)

        self.assertIn("## Overall Metrics", markdown)
        self.assertIn("corpus_roles: challenge-replay", markdown)
        self.assertIn("parameter_axes: SENTENCE_CONFIRM_CHUNKS", markdown)
        self.assertIn("corpus_role: challenge-replay", markdown)
        self.assertIn("case_count: 1113", markdown)
        self.assertIn("expected_final_case_count: 1109", markdown)
        self.assertIn("draft_count: 0", markdown)
        self.assertNotIn("representative_sampling_units", markdown)
        self.assertNotIn("representative_sampling_rules", markdown)
        self.assertNotIn("representative_source_log_count", markdown)
        self.assertIn("failure-enriched", markdown)
        self.assertIn("experiment_stage: challenge-replay", markdown)
        self.assertIn("experiment_stage_description: failure reproduction", markdown)
        self.assertIn("evidence_use: failure replay lifecycle trade-off analysis", markdown)
        self.assertIn("claim_scope_key: failure-lifecycle-tradeoff", markdown)
        self.assertIn("claim_scope: failure-mode lifecycle trade-off only", markdown)
        self.assertIn("supported_claims: revision lifecycle trade-off on observed failure cases", markdown)
        self.assertIn("unsupported_claims: operating-average quality", markdown)
        self.assertIn("deferred_claims: operating-average finalization quality", markdown)
        self.assertIn("runtime: sat + cuda + float16", markdown)
        self.assertIn("model_source: local-cache-only", markdown)
        self.assertIn("offline_model_env: HF_HUB_OFFLINE=1, TRANSFORMERS_OFFLINE=1", markdown)
        self.assertIn("lifecycle_state_machine_parity: partial", markdown)
        self.assertIn(
            "lifecycle_runtime_state_owner: "
            "src.app.dictation_node_sentence_candidate_commit_buffer.SentenceCandidateCommitBufferNode",
            markdown,
        )
        self.assertIn(
            "lifecycle_replay_state_owner: tests.eval.dictation_ai.sbd_benchmark.LifecycleState",
            markdown,
        )
        self.assertIn("lifecycle_replayed_runtime_signals: stable_analysis.stable_internal_ratio", markdown)
        self.assertIn("lifecycle_missing_runtime_signals: audio timestamp latency", markdown)
        self.assertIn("paper_evidence_requested: true", markdown)
        self.assertIn("paper_evidence: true", markdown)
        self.assertIn("paper_evidence_eligible: true", markdown)
        self.assertIn("required_evidence_fields: evidence_protocol.paper_evidence", markdown)
        self.assertIn("runtime_contract.device", markdown)
        self.assertIn("case_summary.expected_final_case_count", markdown)
        self.assertIn("evidence_summary", markdown)
        self.assertIn("missing_required_evidence_fields: none", markdown)
        self.assertIn("## Evidence Summary", markdown)
        self.assertIn("| sentence_confirm_chunks-1 | AVC_DICTATION_SENTENCE_CONFIRM_CHUNKS=1 | +0.1000 | -0.2000 | +0.3000 |  |", markdown)
        self.assertIn(
            "| sentence_confirm_chunks-1 | review-risk | overall-final-f1-up-precision-down, language-final-f1-regression, language-precision-regression |",
            markdown,
        )
        self.assertIn("| interpretation_flag | count |", markdown)
        self.assertIn("| adoption_review | count |", markdown)
        self.assertIn("| review-risk | 1 |", markdown)
        self.assertIn("| overall-final-f1-up-precision-down | 1 |", markdown)
        self.assertIn("| sentence_confirm_chunks-1 | ko | -0.1000 | -0.2000 |  | -2.0000 | +1.0000 |", markdown)
        self.assertIn("| sentence_confirm_chunks-1 | missing-final | +0.2000 |  |  | -2.0000 | +1.0000 |", markdown)
        self.assertIn("| baseline | 10 | 8 | 7 | 5 | 4 | 8 | 2 | 1 |", markdown)
        self.assertIn("| sentence_confirm_chunks-1 | 7 | 7 | 9 | 9 | 2 | 3 | 3 | 1 |", markdown)
        self.assertIn(
            "| label | queue_residue_cases | queue_residue_total | queue_residue_avg_when_present | queue_residue_max | queue_len_ge_2 | queue_len_ge_5 | active_staged_residue | pending_residue |",
            markdown,
        )
        self.assertIn("| baseline | 6 | 12 | 2.0000 | 4 | 3 | 0 | 9 | 8 |", markdown)
        self.assertIn("| sentence_confirm_chunks-1 | 5 | 15 | 3.0000 | 6 | 4 | 1 | 7 | 6 |", markdown)
        self.assertIn(
            "| label | top_queue_case | queue_len | queue_revision | replace_deferred | final_f1 | boundary_f1 | active_staged | pending |",
            markdown,
        )
        self.assertIn("| baseline | baseline-queue-heavy | 4 | 8 | 10 | 0.2000 | 0.0000 | true | true |", markdown)
        self.assertIn("| sentence_confirm_chunks-1 | override-queue-heavy | 6 | 7 | 7 | 0.3000 | 0.1000 | false | true |", markdown)
        self.assertIn(
            "| label | queue_stratum | cases | final_f1 | boundary_f1 | staged_residue | empty_final | queue_revision | replace_deferred |",
            markdown,
        )
        self.assertIn("| baseline | queue_len_ge_5 | 1 | 0.1000 | 0.0000 | 1 | 1 | 6 | 7 |", markdown)
        self.assertIn("| sentence_confirm_chunks-1 | no_queue | 91 | 0.7000 | 0.4000 | 4 | 1 | 1 | 1 |", markdown)
        self.assertIn(
            "| label | lifecycle_focus_cases | lifecycle_without_input_review_cases | input_contamination_review_cases |",
            markdown,
        )
        self.assertIn("| baseline | 100 | 96 | 4 |", markdown)
        self.assertIn("| sentence_confirm_chunks-1 | 100 | 95 | 5 |", markdown)
        self.assertIn(
            "| sentence_confirm_chunks-1 | +0.1000 | -0.0200 | -2.0000 | -0.1000 | -0.1000 |",
            markdown,
        )
        self.assertIn(
            "| baseline | baseline-heavy | 10.0000 | 3 | 5 | 2 | 0.2000 | 0.0000 |",
            markdown,
        )
        self.assertIn(
            "| sentence_confirm_chunks-1 | override-heavy | 11.0000 | 4 | 6 | 1 | 0.3000 | 0.1000 |",
            markdown,
        )
        self.assertIn(
            "| sentence_confirm_chunks-1 | -3.0000 | -1.0000 | +2.0000 | +4.0000 | -2.0000 | -5.0000 | +1.0000 | +0.0000 |",
            markdown,
        )
        self.assertIn(
            "| sentence_confirm_chunks-1 | -1.0000 | +3.0000 | +1.0000 | +2.0000 | +1.0000 | +1.0000 | -2.0000 | -2.0000 |",
            markdown,
        )
        self.assertIn(
            "| sentence_confirm_chunks-1 | no_queue | +0.1000 | +0.1000 | -1.0000 | -1.0000 | +0.0000 | -1.0000 |",
            markdown,
        )
        self.assertIn("sentence_confirm_chunks-1", markdown)
        self.assertIn("0.6000 (+0.1000)", markdown)
        self.assertIn("0.4000 (-0.1000)", markdown)
        self.assertIn("1 (-2.0000)", markdown)
        self.assertIn("## Tag Metrics", markdown)
        self.assertIn("missing-final", markdown)
        self.assertIn("0.7000 (+0.2000)", markdown)

    def test_render_markdown_summary_includes_representative_sampling_context(self) -> None:
        payload = {
            "dry_run": False,
            "corpus_roles": ["representative"],
            "parameter_axes": ["SENTENCE_CONFIRM_CHUNKS"],
            "runtime_contract": {
                "backend": "sat",
                "device": "cuda",
                "compute_type": "float16",
                "offline_model_env": {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"},
                "model_source": "local-cache-only",
            },
            "evidence_protocol": {
                "paper_evidence_requested": True,
                "paper_evidence": True,
                "paper_evidence_eligible": True,
                "corpus_role": "representative",
                "corpus_interpretation": "representative operating sample",
                "experiment_stage": "representative-replay",
                "experiment_stage_description": "operating-average finalization estimate for a documented time/session sample",
                "evidence_use": "operating-average estimate",
                "claim_scope_key": "operating-average-finalization",
                "claim_scope": "operating-average finalization estimate only",
                "supported_claims": [
                    "operating-average finalization estimate for the sampled population",
                    "representative finalization metric decomposition",
                ],
                "unsupported_claims": [
                    "failure-mode regression coverage",
                    "parameter adoption without challenge replay regression check",
                ],
                "deferred_claims": [
                    "translation-side churn reduction",
                    "raw ASR accuracy comparison",
                ],
                "required_evidence_fields": [
                    "evidence_protocol.supported_claims",
                    "evidence_protocol.unsupported_claims",
                    "evidence_protocol.deferred_claims",
                    "case_summary.representative_metadata.sampling_unit_counts",
                    "case_summary.representative_metadata.sampling_rule_counts",
                    "case_summary.representative_metadata.source_log_count",
                    "case_summary.representative_metadata.review_packet_count",
                    "case_summary.representative_metadata.expected_final_reviewer_counts",
                    "case_summary.representative_review_packet_validation.packet_count",
                    "case_summary.representative_review_packet_validation.ready_packet_count",
                    "case_summary.representative_review_packet_validation.matched_case_count",
                ],
                "missing_required_evidence_fields": [],
            },
            "case_summary": {
                "corpus_role": "representative",
                "case_count": 2,
                "expected_final_case_count": 2,
                "draft_count": 0,
                "representative_metadata": {
                    "sampling_unit_counts": {"session-window": 1, "time-window": 1},
                    "sampling_rule_counts": {"fixed-interval-10min": 2},
                    "source_log_count": 2,
                    "review_packet_count": 2,
                    "expected_final_reviewer_counts": {"human-reviewed": 2},
                },
                "representative_review_packet_validation": {
                    "packet_count": 2,
                    "ready_packet_count": 2,
                    "matched_case_count": 2,
                },
            },
            "jobs": [{"label": "baseline"}],
            "evidence_summary": {"results": [], "adoption_review_counts": {}},
            "results": [
                {
                    "label": "baseline",
                    "env_overrides": {},
                    "metrics": {},
                    "metric_deltas": {},
                    "language_summary": {},
                    "language_deltas": {},
                    "tag_summary": {},
                    "tag_deltas": {},
                }
            ],
        }

        markdown = render_markdown_summary(payload)

        self.assertIn("representative_sampling_units: session-window=1, time-window=1", markdown)
        self.assertIn("representative_sampling_rules: fixed-interval-10min=2", markdown)
        self.assertIn("representative_source_log_count: 2", markdown)
        self.assertIn("representative_review_packet_count: 2", markdown)
        self.assertIn("representative_reviewers: human-reviewed=2", markdown)
        self.assertIn("representative_review_packet_validation_packet_count: 2", markdown)
        self.assertIn("representative_review_packet_validation_ready_packet_count: 2", markdown)
        self.assertIn("representative_review_packet_validation_matched_case_count: 2", markdown)
        self.assertIn("supported_claims: operating-average finalization estimate for the sampled population", markdown)
        self.assertIn("unsupported_claims: failure-mode regression coverage", markdown)
        self.assertIn("deferred_claims: translation-side churn reduction", markdown)

    def test_dry_run_summary_preserves_case_corpus_role(self) -> None:
        jobs = [
            SweepJob(
                label="baseline",
                output=Path("out/baseline.json"),
                argv=("python", "benchmark.py"),
                env_overrides={},
            )
        ]
        payload = build_summary_payload(
            jobs,
            dry_run=True,
            paper_evidence=True,
            case_summary={
                "case_count": 1113,
                "expected_final_case_count": 1109,
                "corpus_role": "challenge-replay",
            },
        )

        self.assertEqual(payload["case_summary"]["corpus_role"], "challenge-replay")
        self.assertEqual(payload["parameter_axes"], [])
        self.assertEqual(
            payload["runtime_contract"]["offline_model_env"],
            {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"},
        )
        self.assertEqual(payload["corpus_roles"], ["challenge-replay"])
        self.assertTrue(payload["evidence_protocol"]["paper_evidence_requested"])
        self.assertTrue(payload["evidence_protocol"]["dry_run"])
        self.assertFalse(payload["evidence_protocol"]["paper_evidence"])
        self.assertFalse(payload["evidence_protocol"]["paper_evidence_eligible"])
        self.assertEqual(payload["evidence_protocol"]["evidence_use"], "failure replay lifecycle trade-off analysis")
        self.assertEqual(
            payload["evidence_protocol"]["missing_required_evidence_fields"],
            ["evidence_summary.results", "evidence_summary.adoption_review_counts"],
        )

    def test_summary_payload_records_parameter_axes(self) -> None:
        jobs = [
            SweepJob(
                label="baseline",
                output=Path("out/baseline.json"),
                argv=("python", "benchmark.py"),
                env_overrides={},
            ),
            SweepJob(
                label="sentence_confirm_chunks-1",
                output=Path("out/sentence_confirm_chunks-1.json"),
                argv=("python", "benchmark.py"),
                env_overrides={"AVC_DICTATION_SENTENCE_CONFIRM_CHUNKS": "1"},
            ),
            SweepJob(
                label="sentence_confirm_chunks-3",
                output=Path("out/sentence_confirm_chunks-3.json"),
                argv=("python", "benchmark.py"),
                env_overrides={"AVC_DICTATION_SENTENCE_CONFIRM_CHUNKS": "3"},
            ),
        ]
        payload = build_summary_payload(jobs, dry_run=True)

        self.assertEqual(payload["parameter_axes"], ["SENTENCE_CONFIRM_CHUNKS"])

    def test_paper_evidence_mode_requires_reviewed_finalization_case_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sbd_cases"
            language_dir = root / "ko"
            language_dir.mkdir(parents=True)
            cases = language_dir / "reviewed-context-ko-a.jsonl"
            cases.write_text(
                json.dumps(
                    {
                        "id": "case-1",
                        "language": "ko",
                        "chunks": ["안녕하세요."],
                        "expected_final": ["안녕하세요."],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            with patch("tests.eval.dictation_ai.cases.sbd_case_paths.SBD_CHALLENGE_CASE_DIR", root):
                with self.assertRaisesRegex(ValueError, "expected-final case count below target"):
                    validate_sweep_case_set((root,), paper_evidence=True, min_expected_final_cases=None)

    def test_paper_evidence_representative_requires_explicit_case_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sbd_representative_cases"
            root.mkdir(parents=True)
            cases = root / "representative.jsonl"
            review_packets = Path(tmp) / "review-packets.json"
            cases.write_text(
                json.dumps(
                    {
                        "id": "representative-1",
                        "corpus_role": "representative",
                        "sampling_unit": "time-window",
                        "sampling_rule": "fixed-interval-10min",
                        "source_log": ".tmp/logs/avc-whisper.log",
                        "source_started_at": "chunk:1",
                        "source_ended_at": "chunk:3",
                        "language": "ko",
                        "stt_backend": "faster-whisper",
                        "stt_model": "large-v3",
                        "window_seconds": 10.0,
                        "step_seconds": 1.0,
                        "sentence_finalize_age": 3,
                        "review_packet_id": "ko_representative_review_abc",
                        "expected_final_reviewed_by": "human-reviewed",
                        "chunks": ["안녕하세요."],
                        "expected_final": ["안녕하세요."],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            self._write_review_packets(review_packets)

            with patch("tests.eval.dictation_ai.cases.sbd_case_paths.SBD_REPRESENTATIVE_CASE_DIR", root):
                with self.assertRaisesRegex(ValueError, "requires explicit --min-expected-final-cases"):
                    validate_sweep_case_set((root,), paper_evidence=True, min_expected_final_cases=None)

                with self.assertRaisesRegex(ValueError, "requires --review-packets"):
                    validate_sweep_case_set((root,), paper_evidence=True, min_expected_final_cases=1)

                summary = validate_sweep_case_set(
                    (root,),
                    paper_evidence=True,
                    min_expected_final_cases=1,
                    review_packets=review_packets,
                )

        self.assertEqual(summary["corpus_role"], "representative")
        self.assertEqual(summary["expected_final_case_count"], 1)
        self.assertEqual(summary["representative_review_packet_validation"]["matched_case_count"], 1)

    def test_paper_evidence_mode_requires_baseline_job(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires --include-baseline"):
            validate_sweep_execution_contract(
                paper_evidence=True,
                include_baseline=False,
                parameters=(parse_sweep_parameter("SENTENCE_CONFIRM_CHUNKS=1"),),
            )

        validate_sweep_execution_contract(
            paper_evidence=True,
            include_baseline=True,
            parameters=(parse_sweep_parameter("SENTENCE_CONFIRM_CHUNKS=1"),),
        )
        validate_sweep_execution_contract(
            paper_evidence=False,
            include_baseline=False,
            parameters=(parse_sweep_parameter("SENTENCE_CONFIRM_CHUNKS=1"),),
        )

    def test_paper_evidence_mode_requires_single_parameter_axis(self) -> None:
        with self.assertRaisesRegex(ValueError, "one parameter axis"):
            validate_sweep_execution_contract(
                paper_evidence=True,
                include_baseline=True,
                parameters=(
                    parse_sweep_parameter("SENTENCE_CONFIRM_CHUNKS=1"),
                    parse_sweep_parameter("SHORT_NO_END_FRAGMENT_UNITS=5"),
                ),
            )

        validate_sweep_execution_contract(
            paper_evidence=True,
            include_baseline=True,
            parameters=(
                parse_sweep_parameter("SENTENCE_CONFIRM_CHUNKS=1"),
                parse_sweep_parameter("SENTENCE_CONFIRM_CHUNKS=3"),
            ),
        )

    def test_paper_evidence_mode_rejects_exploratory_case_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cases = Path(tmp) / "cases.jsonl"
            cases.write_text(
                json.dumps(
                    {
                        "id": "case-1",
                        "language": "ko",
                        "chunks": ["안녕하세요."],
                        "expected_final": ["안녕하세요."],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "requires a challenge-replay or representative corpus"):
                validate_sweep_case_set((cases,), paper_evidence=True, min_expected_final_cases=1)

    def test_exploratory_sweep_rejects_draft_cases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cases = Path(tmp) / "cases.jsonl"
            cases.write_text(
                json.dumps(
                    {
                        "id": "case-1",
                        "language": "ko",
                        "chunks": ["안녕하세요."],
                        "expected_final": ["안녕하세요."],
                        "draft_expected_final_required": True,
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "unreviewed draft"):
                validate_sweep_case_set((cases,), paper_evidence=False, min_expected_final_cases=None)


if __name__ == "__main__":
    unittest.main()
