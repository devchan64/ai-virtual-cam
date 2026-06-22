import unittest
from argparse import Namespace
from io import StringIO
from unittest.mock import patch

from tests.eval.dictation_ai import sbd_benchmark
from tests.eval.dictation_ai.benchmark.sbd_benchmark_report import (
    build_benchmark_report,
    summarize_case_exemplars,
    summarize_results_by_input_evidence_strata,
    summarize_results_by_expected_quality_strata,
    summarize_results_by_queue_residue_strata,
    summarize_results_by_evidence_strata,
    summarize_lifecycle_bottlenecks,
    summarize_results_by_language,
    summarize_results_by_tag,
    summarize_staged_queue_residue,
)
from tests.eval.dictation_ai.cases.sbd_case_loader import SbdCase


def _score(precision: float, recall: float, f1: float, *, exact: bool = False) -> dict[str, object]:
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "similarity_coverage": f1,
        "exact": exact,
    }


class DictationAiSbdBenchmarkReportTest(unittest.TestCase):
    def test_cli_main_prints_runtime_errors_without_traceback(self) -> None:
        stderr = StringIO()

        with patch.object(sbd_benchmark, "main", side_effect=RuntimeError("No CUDA GPUs are available")), patch(
            "sys.stderr",
            stderr,
        ):
            exit_code = sbd_benchmark.cli_main()

        self.assertEqual(exit_code, 1)
        self.assertEqual(
            stderr.getvalue().strip(),
            "[dictation-ai-sbd-benchmark] error: No CUDA GPUs are available",
        )

    def test_benchmark_report_includes_evidence_protocol(self) -> None:
        args = Namespace(
            model="sat-3l-sm",
            device="cuda",
            compute_type="float16",
            min_final_f1=0.0,
            fail_on_regression=False,
        )
        case = SbdCase(
            id="case-a",
            language="ko",
            chunks=["안녕하세요.", "안녕하세요. 반갑습니다."],
            expected_completed=[],
            expected_pending="",
            expected_final=["안녕하세요.", "반갑습니다."],
            expected_staged="",
            tags=("missing-final",),
            sentence_finalize_age=3,
        )
        results = [
            {
                "id": "case-a",
                "language": "ko",
                "tags": ["missing-final"],
                "expected_final": ["안녕하세요.", "반갑습니다."],
                "chunks": [{"input": "안녕하세요."}, {"input": "안녕하세요. 반갑습니다."}],
                "actual_final": ["안녕하세요.", "반갑습니다."],
                "actual_pending": "",
                "actual_staged": "",
                "actual_staged_queue": [],
                "final_score": _score(1.0, 1.0, 1.0, exact=True),
                "final_boundary_score": _score(1.0, 1.0, 1.0, exact=True),
                "completed_last_score": _score(1.0, 1.0, 1.0),
                "pending_exact": True,
                "staged_exact": True,
                "case_exact_match": True,
                "metrics": {
                    "finalized": 2,
                    "stage_start": 2,
                    "stage_age_hold": 2,
                    "pending_overrun": 1,
                    "pending_quality_repeated_word_ngram": 1,
                    "stage_candidate_quality_repeated_word_ngram": 1,
                    "stage_replace_decision_open_latin_clause": 1,
                },
            }
        ]

        report = build_benchmark_report(
            args=args,
            case_sources=["cases.jsonl"],
            corpus_role="challenge-replay",
            cases=[case],
            results=results,
            metric_totals={
                "finalized": 2,
                "stage_start": 2,
                "stage_age_hold": 2,
                "pending_overrun": 1,
                "pending_quality_repeated_word_ngram": 1,
                "stage_candidate_quality_repeated_word_ngram": 1,
                "stage_replace_decision_open_latin_clause": 1,
            },
            elapsed_ms=12.345,
        )

        protocol = report["evidence_protocol"]
        self.assertEqual(report["corpus_role"], "challenge-replay")
        self.assertEqual(
            report["case_summary"],
            {
                "case_count": 1,
                "corpus_role": "challenge-replay",
                "expected_final_case_count": 1,
                "draft_count": 0,
            },
        )
        self.assertFalse(protocol["paper_evidence"])
        self.assertTrue(protocol["paper_evidence_corpus_eligible"])
        self.assertFalse(protocol["paper_evidence_eligible"])
        self.assertEqual(protocol["evidence_use"], "failure replay lifecycle trade-off analysis")
        self.assertEqual(protocol["claim_scope_key"], "failure-lifecycle-tradeoff")
        self.assertEqual(protocol["claim_scope"], "failure-mode lifecycle trade-off only")
        self.assertIn("revision lifecycle trade-off on observed failure cases", protocol["supported_claims"])
        self.assertIn("operating-average quality", protocol["unsupported_claims"])
        self.assertIn("translation-side churn reduction", protocol["deferred_claims"])
        self.assertIn("not an operating-average quality estimate", protocol["limitations"])
        self.assertEqual(
            protocol["missing_required_evidence_fields"],
            ["parameter_axes", "evidence_summary.results", "evidence_summary.adoption_review_counts"],
        )
        self.assertIn("evidence_protocol.claim_scope_key", protocol["required_evidence_fields"])
        self.assertIn("evidence_protocol.supported_claims", protocol["required_evidence_fields"])
        self.assertIn("evidence_protocol.unsupported_claims", protocol["required_evidence_fields"])
        self.assertIn("evidence_protocol.deferred_claims", protocol["required_evidence_fields"])
        self.assertIn("runtime_contract.compute_type", protocol["required_evidence_fields"])
        self.assertIn("case_summary.expected_final_case_count", protocol["required_evidence_fields"])
        self.assertEqual(
            report["regression_guard"],
            {
                "enabled": False,
                "min_final_f1": 0.0,
                "metric": "final_f1_avg",
                "paper_metric": False,
            },
        )
        self.assertEqual(
            report["runtime_contract"]["offline_model_env"],
            {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"},
        )
        self.assertEqual(report["runtime_contract"]["model_source"], "local-cache-only")
        self.assertEqual(report["lifecycle_replay_contract"]["state_machine_parity"], "partial")
        self.assertEqual(
            report["lifecycle_replay_contract"]["runtime_state_owner"],
            "src.app.dictation_node_sentence_candidate_commit_buffer.SentenceCandidateCommitBufferNode",
        )
        self.assertEqual(
            report["lifecycle_replay_contract"]["replay_state_owner"],
            "tests.eval.dictation_ai.sbd_benchmark.LifecycleState",
        )
        self.assertIn(
            "src.app.dictation_transcript_logic._sentences_are_revisions",
            report["lifecycle_replay_contract"]["shared_decision_helpers"],
        )
        self.assertIn(
            "stable_analysis.stable_internal_ratio",
            report["lifecycle_replay_contract"]["replayed_runtime_signals"],
        )
        self.assertIn(
            "audio timestamp latency",
            report["lifecycle_replay_contract"]["missing_runtime_signals"],
        )
        self.assertNotIn("min_final_f1", report["summary"])
        self.assertEqual(report["summary"]["final_f1_avg"], 1.0)
        self.assertEqual(report["summary"]["finalized_per_stage_start"], 1.0)
        self.assertEqual(report["evidence_strata_summary"]["all_cases"]["case_count"], 1)
        self.assertEqual(report["evidence_strata_summary"]["lifecycle_focus"]["case_count"], 1)
        self.assertEqual(report["evidence_strata_summary"]["input_contamination_review"]["case_count"], 0)
        self.assertEqual(
            report["expected_quality_strata_summary"]["expected_quality_review"]["case_count"],
            0,
        )
        self.assertEqual(
            report["expected_quality_strata_summary"]["without_expected_quality_review"]["case_count"],
            1,
        )
        self.assertEqual(
            report["input_evidence_strata_summary"]["full_input_evidence"]["case_count"],
            1,
        )
        self.assertEqual(
            report["input_evidence_strata_summary"]["partial_input_evidence_review"]["case_count"],
            0,
        )
        self.assertEqual(
            report["input_evidence_strata_summary"]["weak_input_evidence_review"]["case_count"],
            0,
        )
        self.assertEqual(report["context_strata_summary"]["clean_context"]["case_count"], 1)
        self.assertEqual(report["context_strata_summary"]["context_definition_review"]["case_count"], 0)
        self.assertEqual(report["collection_strata_summary"]["manual_named_case"]["case_count"], 1)
        strict_summary = report["strict_logic_candidate_summary"]
        self.assertEqual(strict_summary["strict_case_count"], 1)
        self.assertEqual(strict_summary["summary"]["final_f1_avg"], 1.0)
        self.assertEqual(strict_summary["collection_strata"]["manual_named_case"]["case_count"], 1)
        self.assertEqual(report["cases"][0]["expected_quality_flags"], [])
        self.assertEqual(report["cases"][0]["case_context_flags"], [])
        self.assertEqual(report["cases"][0]["case_definition_flags"], [])
        self.assertTrue(report["cases"][0]["input_evidence"]["has_evidence"])
        self.assertTrue(report["cases"][0]["input_evidence"]["fully_supported"])
        self.assertEqual(report["cases"][0]["input_evidence"]["covered_count"], 2)
        self.assertEqual(report["case_definition_strata_summary"]["clean_case_definition"]["case_count"], 1)
        self.assertEqual(report["case_definition_strata_summary"]["case_definition_review"]["case_count"], 0)
        self.assertEqual(report["case_definition_action_summary"]["review_case_count"], 0)
        self.assertEqual(report["case_exemplar_summary"]["lifecycle_focus_top"][0]["id"], "case-a")
        self.assertEqual(report["staged_queue_residue_summary"]["queue_residue_case_count"], 0)
        self.assertEqual(report["staged_queue_residue_summary"]["active_staged_residue_case_count"], 0)
        self.assertEqual(report["lifecycle_bottleneck_summary"]["metrics"]["stage_start"], 2)
        self.assertEqual(report["lifecycle_bottleneck_summary"]["metrics"]["stage_age_hold"], 2)
        self.assertEqual(report["lifecycle_bottleneck_summary"]["metrics"]["pending_overrun"], 1)
        self.assertEqual(
            report["lifecycle_bottleneck_summary"]["metrics"]["pending_quality_repeated_word_ngram"],
            1,
        )
        self.assertIn(
            "stage_candidate_quality_repeated_word_ngram",
            report["lifecycle_bottleneck_summary"]["metric_keys"],
        )
        self.assertEqual(
            report["lifecycle_bottleneck_summary"]["metrics"]["stage_replace_decision_open_latin_clause"],
            1,
        )
        stage_age_hold_presence = report["lifecycle_bottleneck_summary"]["metric_presence_summary"]["stage_age_hold"]
        self.assertEqual(stage_age_hold_presence["total_count"], 2)
        self.assertEqual(stage_age_hold_presence["case_count_present"], 1)
        self.assertEqual(stage_age_hold_presence["case_count_absent"], 0)
        self.assertEqual(stage_age_hold_presence["final_f1_avg_present"], 1.0)
        self.assertEqual(stage_age_hold_presence["low_final_f1_present_count"], 0)
        dynamic_presence = report["lifecycle_bottleneck_summary"]["metric_presence_summary"][
            "stage_candidate_quality_repeated_word_ngram"
        ]
        self.assertEqual(dynamic_presence["total_count"], 1)
        self.assertEqual(dynamic_presence["case_count_present"], 1)
        self.assertEqual(
            report["lifecycle_bottleneck_summary"]["by_language"]["ko"]["expected_final_count"],
            2,
        )

    def test_report_summarizes_low_score_review_needed_cases(self) -> None:
        args = Namespace(
            model="sat-3l-sm",
            device="cuda",
            compute_type="float16",
            min_final_f1=0.0,
            fail_on_regression=False,
        )
        case = SbdCase(
            id="case-review-needed",
            language="en",
            chunks=["A later sentence appears here."],
            expected_completed=[],
            expected_pending="",
            expected_final=["The missing earlier sentence.", "A later sentence appears here."],
            expected_staged="",
            tags=("missing-final", "stage-queue"),
            sentence_finalize_age=3,
        )
        supported_case = SbdCase(
            id="case-supported-monotonic",
            language="zh",
            chunks=["第一句到了。", "第一句到了。第二句也到了。"],
            expected_completed=[],
            expected_pending="",
            expected_final=["第一句到了。", "第二句也到了。"],
            expected_staged="",
            tags=("missing-final", "stage-queue"),
            sentence_finalize_age=3,
        )
        unmodeled_prefix_case = SbdCase(
            id="case-unmodeled-prefix",
            language="en",
            chunks=["This part already ended. Target sentence arrived. Another sentence arrived."],
            expected_completed=[],
            expected_pending="",
            expected_final=["Target sentence arrived.", "Another sentence arrived."],
            expected_staged="",
            tags=("missing-final", "stage-queue"),
            sentence_finalize_age=3,
        )
        results = [
            {
                "id": "case-review-needed",
                "language": "en",
                "tags": ["missing-final", "stage-queue"],
                "expected_final": ["The missing earlier sentence.", "A later sentence appears here."],
                "actual_final": [],
                "actual_pending": "",
                "actual_staged": "A later sentence appears here.",
                "actual_staged_queue": ["The missing earlier sentence."],
                "final_score": _score(0.0, 0.0, 0.0),
                "final_ordered_score": _score(0.0, 0.0, 0.0),
                "final_boundary_score": _score(0.0, 0.0, 0.0),
                "completed_last_score": _score(0.0, 0.0, 0.0),
                "pending_exact": True,
                "staged_exact": False,
                "case_exact_match": False,
                "metrics": {
                    "stage_start": 1,
                    "stage_queue_revision": 2,
                    "stage_candidate_quality_blocked": 1,
                },
            },
            {
                "id": "case-supported-monotonic",
                "language": "zh",
                "tags": ["missing-final", "stage-queue"],
                "expected_final": ["第一句到了。", "第二句也到了。"],
                "chunks": [{"input": "第一句到了。"}, {"input": "第一句到了。第二句也到了。"}],
                "actual_final": ["第一句到了。"],
                "actual_pending": "",
                "actual_staged": "第二句也到了。",
                "actual_staged_queue": [],
                "final_score": _score(0.5, 0.25, 0.3333333333),
                "final_ordered_score": _score(0.5, 0.25, 0.3333333333),
                "final_boundary_score": _score(0.0, 0.0, 0.0),
                "completed_last_score": _score(0.0, 0.0, 0.0),
                "pending_exact": True,
                "staged_exact": False,
                "case_exact_match": False,
                "metrics": {
                    "stage_start": 1,
                    "stage_queue_revision": 1,
                    "stage_age_hold": 2,
                    "stage_candidate_quality_blocked": 1,
                    "candidate_recent_final_delta_trimmed": 1,
                },
            },
            {
                "id": "case-unmodeled-prefix",
                "language": "en",
                "tags": ["missing-final", "stage-queue"],
                "expected_final": ["Target sentence arrived.", "Another sentence arrived."],
                "chunks": [{"input": "This part already ended. Target sentence arrived. Another sentence arrived."}],
                "actual_final": ["This part already ended."],
                "actual_pending": "",
                "actual_staged": "Target sentence arrived.",
                "actual_staged_queue": [],
                "final_score": _score(0.0, 0.0, 0.0),
                "final_ordered_score": _score(0.0, 0.0, 0.0),
                "final_boundary_score": _score(0.0, 0.0, 0.0),
                "completed_last_score": _score(0.0, 0.0, 0.0),
                "pending_exact": True,
                "staged_exact": False,
                "case_exact_match": False,
                "metrics": {
                    "stage_start": 1,
                    "stage_queue_revision": 1,
                    "stage_candidate_quality_blocked": 1,
                },
            },
        ]

        report = build_benchmark_report(
            args=args,
            case_sources=["cases.jsonl"],
            corpus_role="challenge-replay",
            cases=[case, supported_case, unmodeled_prefix_case],
            results=results,
            metric_totals={
                "stage_start": 3,
                "stage_queue_revision": 4,
                "stage_candidate_quality_blocked": 2,
                "candidate_recent_final_delta_trimmed": 1,
                "stage_age_hold": 2,
            },
            elapsed_ms=1.0,
        )

        low_score = report["low_score_characteristics_summary"]["thresholds"]["0.35"]
        self.assertEqual(low_score["case_count"], 3)
        self.assertEqual(low_score["support_kind_counts"], {"review_needed": 1, "supported_monotonic": 2})
        self.assertEqual(low_score["language_counts"], {"en": 2, "zh": 1})
        self.assertEqual(low_score["staged_residue_count"], 3)
        self.assertEqual(low_score["by_support_kind"]["review_needed"]["case_count"], 1)
        self.assertEqual(low_score["by_support_kind"]["supported_monotonic"]["case_count"], 2)
        self.assertAlmostEqual(low_score["by_support_kind"]["supported_monotonic"]["avg_final_f1"], 0.16666666665)
        self.assertEqual(low_score["by_support_kind"]["supported_monotonic"]["staged_residue_count"], 2)
        self.assertEqual(low_score["top_lifecycle_metrics"][0]["metric"], "stage_queue_revision")
        self.assertEqual(low_score["lowest_cases"][0]["support_kind"], "review_needed")
        supported_low = report["supported_low_bottleneck_intersection_summary"]["thresholds"]["0.35"]
        self.assertEqual(supported_low["case_count"], 2)
        clean_low = report["clean_low_bottleneck_intersection_summary"]["thresholds"]["0.35"]
        self.assertEqual(clean_low["case_count"], 1)
        self.assertEqual(clean_low["lowest_cases"][0]["id"], "case-supported-monotonic")
        self.assertEqual(clean_low["lowest_cases"][0]["case_context_flags"], [])
        self.assertEqual(
            report["cases"][2]["case_context_flags"],
            ["unmodeled_prefix_context"],
        )
        self.assertEqual(report["strict_logic_candidate_summary"]["strict_case_count"], 1)
        self.assertEqual(
            supported_low["metric_presence"]["stage_candidate_quality_blocked"]["case_count"],
            2,
        )
        self.assertEqual(
            supported_low["metric_presence"]["candidate_recent_final_delta_trimmed"]["case_count"],
            1,
        )
        self.assertIn(
            {
                "metrics": ["stage_candidate_quality_blocked", "stage_queue_revision"],
                "case_count": 2,
                "case_ratio": 1.0,
                "avg_final_f1": 0.16666666665,
                "avg_ordered_f1": 0.16666666665,
                "avg_boundary_f1": 0.0,
                "top_cases": ["case-unmodeled-prefix", "case-supported-monotonic"],
            },
            supported_low["top_metric_pairs"],
        )

    def test_representative_benchmark_report_preserves_sampling_metadata(self) -> None:
        args = Namespace(
            model="sat-3l-sm",
            device="cuda",
            compute_type="float16",
            min_final_f1=0.0,
            fail_on_regression=False,
        )
        case = SbdCase(
            id="representative-case",
            language="en",
            chunks=["Hello world."],
            expected_completed=[],
            expected_pending="",
            expected_final=["Hello world."],
            expected_staged="",
            tags=("representative",),
            sentence_finalize_age=3,
            metadata={
                "sampling_unit": "time-window",
                "sampling_rule": "fixed-interval-10min",
                "source_log": ".tmp/logs/avc-whisper.log",
                "review_packet_id": "en_representative_review_abc",
                "expected_final_reviewed_by": "human-reviewed",
            },
        )
        results = [
            {
                "id": "representative-case",
                "language": "en",
                "tags": ["representative"],
                "expected_final": ["Hello world."],
                "actual_final": ["Hello world."],
                "actual_pending": "",
                "actual_staged": "",
                "actual_staged_queue": [],
                "final_score": _score(1.0, 1.0, 1.0, exact=True),
                "final_boundary_score": _score(1.0, 1.0, 1.0, exact=True),
                "completed_last_score": _score(1.0, 1.0, 1.0),
                "pending_exact": True,
                "staged_exact": True,
                "case_exact_match": True,
                "metrics": {"finalized": 1, "stage_start": 1},
            }
        ]

        report = build_benchmark_report(
            args=args,
            case_sources=["representative.jsonl"],
            corpus_role="representative",
            cases=[case],
            results=results,
            metric_totals={"finalized": 1, "stage_start": 1},
            elapsed_ms=1.0,
            representative_review_packet_validation={
                "packet_count": 1,
                "ready_packet_count": 1,
                "matched_case_count": 1,
            },
        )

        metadata = report["case_summary"]["representative_metadata"]
        self.assertEqual(metadata["sampling_unit_counts"], {"time-window": 1})
        self.assertEqual(metadata["sampling_rule_counts"], {"fixed-interval-10min": 1})
        self.assertEqual(metadata["source_log_count"], 1)
        self.assertEqual(metadata["source_log_counts"], {".tmp/logs/avc-whisper.log": 1})
        self.assertEqual(metadata["review_packet_count"], 1)
        self.assertEqual(metadata["review_packet_counts"], {"en_representative_review_abc": 1})
        self.assertEqual(metadata["expected_final_reviewer_counts"], {"human-reviewed": 1})
        self.assertEqual(
            report["case_summary"]["representative_review_packet_validation"],
            {"packet_count": 1, "ready_packet_count": 1, "matched_case_count": 1},
        )
        self.assertEqual(report["evidence_protocol"]["claim_scope_key"], "operating-average-finalization")
        self.assertIn(
            "operating-average finalization estimate for the sampled population",
            report["evidence_protocol"]["supported_claims"],
        )
        self.assertIn("failure-mode regression coverage", report["evidence_protocol"]["unsupported_claims"])
        self.assertIn("translation-side churn reduction", report["evidence_protocol"]["deferred_claims"])
        missing = report["evidence_protocol"]["missing_required_evidence_fields"]
        self.assertNotIn("case_summary.representative_metadata.sampling_unit_counts", missing)
        self.assertNotIn("case_summary.representative_metadata.sampling_rule_counts", missing)
        self.assertNotIn("case_summary.representative_metadata.source_log_count", missing)
        self.assertNotIn("case_summary.representative_metadata.review_packet_count", missing)
        self.assertNotIn("case_summary.representative_metadata.expected_final_reviewer_counts", missing)
        self.assertNotIn("case_summary.representative_review_packet_validation.packet_count", missing)
        self.assertNotIn("case_summary.representative_review_packet_validation.ready_packet_count", missing)
        self.assertNotIn("case_summary.representative_review_packet_validation.matched_case_count", missing)

    def test_expected_quality_strata_separates_review_candidates(self) -> None:
        results = [
            {
                "id": "case-a",
                "expected_final": ["and then unfinished"],
                "actual_final": ["and then unfinished"],
                "actual_pending": "",
                "actual_staged": "",
                "actual_staged_queue": [],
                "final_score": _score(1.0, 1.0, 1.0),
                "final_boundary_score": _score(0.0, 0.0, 0.0),
                "completed_last_score": _score(0.0, 0.0, 0.0),
                "pending_exact": True,
                "staged_exact": True,
                "case_exact_match": False,
                "metrics": {"finalized": 1, "stage_start": 1},
            },
            {
                "id": "case-b",
                "expected_final": ["This sentence is complete enough."],
                "actual_final": ["This sentence is complete enough."],
                "actual_pending": "",
                "actual_staged": "",
                "actual_staged_queue": [],
                "final_score": _score(1.0, 1.0, 1.0),
                "final_boundary_score": _score(1.0, 1.0, 1.0),
                "completed_last_score": _score(1.0, 1.0, 1.0),
                "pending_exact": True,
                "staged_exact": True,
                "case_exact_match": True,
                "metrics": {"finalized": 1, "stage_start": 1},
            },
        ]

        summary = summarize_results_by_expected_quality_strata(results)

        self.assertEqual(summary["expected_quality_review"]["case_count"], 1)
        self.assertEqual(summary["without_expected_quality_review"]["case_count"], 1)
        self.assertEqual(summary["expected_quality_review"]["final_f1_avg"], 1.0)

    def test_input_evidence_strata_separates_weak_input_cases(self) -> None:
        results = [
            {
                "id": "case-a",
                "expected_final": ["The expected sentence is present."],
                "chunks": [{"input": "The expected sentence is present. Next text."}],
                "actual_final": ["The expected sentence is present."],
                "actual_pending": "",
                "actual_staged": "",
                "actual_staged_queue": [],
                "final_score": _score(1.0, 1.0, 1.0),
                "final_boundary_score": _score(1.0, 1.0, 1.0),
                "completed_last_score": _score(1.0, 1.0, 1.0),
                "pending_exact": True,
                "staged_exact": True,
                "case_exact_match": True,
                "metrics": {"finalized": 1, "stage_start": 1},
            },
            {
                "id": "case-b",
                "expected_final": [
                    "The expected sentence is present.",
                    "This target never appears in the replay input.",
                ],
                "chunks": [{"input": "The expected sentence is present. Next text."}],
                "actual_final": ["The expected sentence is present."],
                "actual_pending": "",
                "actual_staged": "",
                "actual_staged_queue": [],
                "final_score": _score(0.5, 0.5, 0.5),
                "final_boundary_score": _score(0.5, 0.5, 0.5),
                "completed_last_score": _score(0.5, 0.5, 0.5),
                "pending_exact": True,
                "staged_exact": True,
                "case_exact_match": False,
                "metrics": {"finalized": 1, "stage_start": 1},
            },
            {
                "id": "case-c",
                "expected_final": ["This target never appears in the replay input."],
                "chunks": [{"input": "Completely unrelated source text."}],
                "actual_final": [],
                "actual_pending": "",
                "actual_staged": "",
                "actual_staged_queue": [],
                "final_score": _score(0.0, 0.0, 0.0),
                "final_boundary_score": _score(0.0, 0.0, 0.0),
                "completed_last_score": _score(0.0, 0.0, 0.0),
                "pending_exact": True,
                "staged_exact": True,
                "case_exact_match": False,
                "metrics": {"finalized": 0, "stage_start": 1},
            },
        ]

        summary = summarize_results_by_input_evidence_strata(results)

        self.assertEqual(summary["full_input_evidence"]["case_count"], 1)
        self.assertEqual(summary["partial_input_evidence_review"]["case_count"], 1)
        self.assertEqual(summary["weak_input_evidence_review"]["case_count"], 1)
        self.assertEqual(summary["full_input_evidence"]["final_f1_avg"], 1.0)
        self.assertEqual(summary["partial_input_evidence_review"]["final_f1_avg"], 0.5)
        self.assertEqual(summary["weak_input_evidence_review"]["final_f1_avg"], 0.0)

    def test_clean_low_excludes_partial_input_evidence_cases(self) -> None:
        args = Namespace(
            model="sat-3l-sm",
            device="cuda",
            compute_type="float16",
            min_final_f1=0.0,
            fail_on_regression=False,
        )
        partial_case = SbdCase(
            id="partial-input-low",
            language="en",
            chunks=["The first expected sentence appears."],
            expected_completed=[],
            expected_pending="",
            expected_final=[
                "The first expected sentence appears.",
                "The second expected sentence is outside the replay window.",
            ],
            expected_staged="",
            tags=("missing-final",),
            sentence_finalize_age=3,
        )
        full_case = SbdCase(
            id="full-input-low",
            language="en",
            chunks=[
                "The first expected sentence appears. The second expected sentence appears too."
            ],
            expected_completed=[],
            expected_pending="",
            expected_final=[
                "The first expected sentence appears.",
                "The second expected sentence appears too.",
            ],
            expected_staged="",
            tags=("missing-final",),
            sentence_finalize_age=3,
        )
        results = [
            {
                "id": "partial-input-low",
                "language": "en",
                "tags": ["missing-final"],
                "expected_final": [
                    "The first expected sentence appears.",
                    "The second expected sentence is outside the replay window.",
                ],
                "chunks": [{"input": "The first expected sentence appears."}],
                "initial_final": [],
                "actual_final": ["Wrong sentence."],
                "actual_pending": "",
                "actual_staged": "",
                "actual_staged_queue": [],
                "final_score": _score(0.0, 0.0, 0.0),
                "final_ordered_score": _score(0.0, 0.0, 0.0),
                "final_boundary_score": _score(0.0, 0.0, 0.0),
                "completed_last_score": _score(0.0, 0.0, 0.0),
                "pending_exact": True,
                "staged_exact": True,
                "case_exact_match": False,
                "metrics": {"stage_start": 1, "stage_candidate_quality_blocked": 1},
            },
            {
                "id": "full-input-low",
                "language": "en",
                "tags": ["missing-final"],
                "expected_final": [
                    "The first expected sentence appears.",
                    "The second expected sentence appears too.",
                ],
                "chunks": [
                    {
                        "input": "The first expected sentence appears. The second expected sentence appears too."
                    }
                ],
                "initial_final": [],
                "actual_final": ["Wrong sentence."],
                "actual_pending": "",
                "actual_staged": "",
                "actual_staged_queue": [],
                "final_score": _score(0.0, 0.0, 0.0),
                "final_ordered_score": _score(0.0, 0.0, 0.0),
                "final_boundary_score": _score(0.0, 0.0, 0.0),
                "completed_last_score": _score(0.0, 0.0, 0.0),
                "pending_exact": True,
                "staged_exact": True,
                "case_exact_match": False,
                "metrics": {"stage_start": 1, "stage_candidate_quality_blocked": 1},
            },
        ]

        report = build_benchmark_report(
            args=args,
            case_sources=["cases.jsonl"],
            corpus_role="challenge-replay",
            cases=[partial_case, full_case],
            results=results,
            metric_totals={"stage_start": 2, "stage_candidate_quality_blocked": 2},
            elapsed_ms=1.0,
        )

        clean_low = report["clean_low_bottleneck_intersection_summary"]["thresholds"]["0.35"]
        self.assertEqual(clean_low["case_count"], 1)
        self.assertEqual(clean_low["lowest_cases"][0]["id"], "full-input-low")
        self.assertEqual(report["strict_logic_candidate_summary"]["strict_case_count"], 1)

    def test_context_strata_flags_unmodeled_prefix_context(self) -> None:
        args = Namespace(
            model="sat-3l-sm",
            device="cuda",
            compute_type="float16",
            min_final_f1=0.0,
            fail_on_regression=False,
        )
        case = SbdCase(
            id="prefix-context-case",
            language="zh",
            chunks=[
                "前面的句子已经结束了。目标句子到了。",
                "目标句子到了。第二句也到了。",
            ],
            expected_completed=[],
            expected_pending="",
            expected_final=["目标句子到了。", "第二句也到了。"],
            expected_staged="",
            tags=("missing-final",),
            sentence_finalize_age=3,
        )
        results = [
            {
                "id": "prefix-context-case",
                "language": "zh",
                "tags": ["missing-final"],
                "expected_final": ["目标句子到了。", "第二句也到了。"],
                "chunks": [
                    {"input": "前面的句子已经结束了。目标句子到了。"},
                    {"input": "目标句子到了。第二句也到了。"},
                ],
                "initial_final": [],
                "actual_final": ["前面的句子已经结束了。", "目标句子到了。"],
                "actual_pending": "",
                "actual_staged": "第二句也到了。",
                "actual_staged_queue": [],
                "final_score": _score(0.5, 0.5, 0.5),
                "final_ordered_score": _score(0.5, 0.5, 0.5),
                "final_boundary_score": _score(0.5, 0.5, 0.5),
                "completed_last_score": _score(0.0, 0.0, 0.0),
                "pending_exact": True,
                "staged_exact": False,
                "case_exact_match": False,
                "metrics": {"finalized": 2, "stage_start": 2},
            }
        ]

        report = build_benchmark_report(
            args=args,
            case_sources=["cases.jsonl"],
            corpus_role="challenge-replay",
            cases=[case],
            results=results,
            metric_totals={"finalized": 2, "stage_start": 2},
            elapsed_ms=1.0,
        )

        self.assertEqual(report["cases"][0]["case_context_flags"], ["unmodeled_prefix_context"])
        self.assertEqual(report["context_strata_summary"]["context_definition_review"]["case_count"], 1)
        self.assertEqual(report["context_strata_summary"]["clean_context"]["case_count"], 0)
        self.assertEqual(
            report["case_definition_action_summary"]["action_counts"],
            {"add_initial_final_or_trim_prefix": 1},
        )
        self.assertEqual(
            report["case_definition_action_summary"]["by_action"]["add_initial_final_or_trim_prefix"]["examples"][0][
                "id"
            ],
            "prefix-context-case",
        )
        self.assertEqual(report["strict_logic_candidate_summary"]["strict_case_count"], 0)

    def test_repeated_expected_groups_are_case_definition_review_not_strict_logic(self) -> None:
        args = Namespace(
            model="sat-3l-sm",
            device="cuda",
            compute_type="float16",
            min_final_f1=0.0,
            fail_on_regression=False,
        )
        cases = [
            SbdCase(
                id="case-a",
                language="en",
                chunks=["Target sentence arrived."],
                expected_completed=[],
                expected_pending="",
                expected_final=["Target sentence arrived."],
                expected_staged="",
                tags=("missing-final",),
                sentence_finalize_age=3,
            ),
            SbdCase(
                id="case-b",
                language="en",
                chunks=["Target sentence arrived."],
                expected_completed=[],
                expected_pending="",
                expected_final=["Target sentence arrived."],
                expected_staged="",
                tags=("missing-final",),
                sentence_finalize_age=3,
            ),
        ]
        results = [
            {
                "id": "case-a",
                "language": "en",
                "tags": ["missing-final"],
                "expected_final": ["Target sentence arrived."],
                "chunks": [{"input": "Target sentence arrived."}],
                "actual_final": ["Target sentence arrived."],
                "actual_pending": "",
                "actual_staged": "",
                "actual_staged_queue": [],
                "final_score": _score(1.0, 1.0, 1.0, exact=True),
                "final_ordered_score": _score(1.0, 1.0, 1.0, exact=True),
                "final_boundary_score": _score(1.0, 1.0, 1.0, exact=True),
                "completed_last_score": _score(1.0, 1.0, 1.0),
                "pending_exact": True,
                "staged_exact": True,
                "case_exact_match": True,
                "metrics": {"finalized": 1, "stage_start": 1},
            },
            {
                "id": "case-b",
                "language": "en",
                "tags": ["missing-final"],
                "expected_final": ["Target sentence arrived."],
                "chunks": [{"input": "Target sentence arrived."}],
                "actual_final": [],
                "actual_pending": "",
                "actual_staged": "Target sentence arrived.",
                "actual_staged_queue": [],
                "final_score": _score(0.0, 0.0, 0.0),
                "final_ordered_score": _score(0.0, 0.0, 0.0),
                "final_boundary_score": _score(0.0, 0.0, 0.0),
                "completed_last_score": _score(0.0, 0.0, 0.0),
                "pending_exact": True,
                "staged_exact": False,
                "case_exact_match": False,
                "metrics": {"stage_start": 1},
            },
        ]

        report = build_benchmark_report(
            args=args,
            case_sources=["cases.jsonl"],
            corpus_role="challenge-replay",
            cases=cases,
            results=results,
            metric_totals={"finalized": 1, "stage_start": 2},
            elapsed_ms=1.0,
        )

        self.assertEqual(report["case_definition_strata_summary"]["case_definition_review"]["case_count"], 2)
        self.assertEqual(report["case_definition_strata_summary"]["clean_case_definition"]["case_count"], 0)
        self.assertEqual(report["cases"][0]["case_definition_flags"], ["repeated_expected_group"])
        self.assertEqual(report["cases"][1]["case_definition_flags"], ["repeated_expected_group"])
        self.assertEqual(
            report["case_definition_action_summary"]["action_counts"],
            {"deduplicate_shifted_window_group": 2},
        )
        self.assertEqual(report["strict_logic_candidate_summary"]["strict_case_count"], 0)
        clean_low = report["clean_low_bottleneck_intersection_summary"]["thresholds"]["0.35"]
        self.assertEqual(clean_low["case_count"], 0)

    def test_fragment_expected_final_is_reported_as_rewrite_action(self) -> None:
        args = Namespace(
            model="sat-3l-sm",
            device="cuda",
            compute_type="float16",
            min_final_f1=0.0,
            fail_on_regression=False,
        )
        case = SbdCase(
            id="fragment-expected",
            language="en",
            chunks=["A complete sentence appears and then it continues."],
            expected_completed=[],
            expected_pending="",
            expected_final=["and then it continues"],
            expected_staged="",
            tags=("missing-final",),
            sentence_finalize_age=3,
        )
        results = [
            {
                "id": "fragment-expected",
                "language": "en",
                "tags": ["missing-final"],
                "expected_final": ["and then it continues"],
                "chunks": [{"input": "A complete sentence appears and then it continues."}],
                "initial_final": [],
                "actual_final": [],
                "actual_pending": "",
                "actual_staged": "and then it continues",
                "actual_staged_queue": [],
                "final_score": _score(0.0, 0.0, 0.0),
                "final_ordered_score": _score(0.0, 0.0, 0.0),
                "final_boundary_score": _score(0.0, 0.0, 0.0),
                "completed_last_score": _score(0.0, 0.0, 0.0),
                "pending_exact": True,
                "staged_exact": False,
                "case_exact_match": False,
                "metrics": {"stage_start": 1},
            }
        ]

        report = build_benchmark_report(
            args=args,
            case_sources=["cases.jsonl"],
            corpus_role="challenge-replay",
            cases=[case],
            results=results,
            metric_totals={"stage_start": 1},
            elapsed_ms=1.0,
        )

        action_summary = report["case_definition_action_summary"]
        self.assertEqual(
            action_summary["action_counts"],
            {
                "manual_boundary_review": 1,
                "rewrite_fragment_expected_final": 1,
            },
        )
        self.assertIn("lowercase_or_connector_start", action_summary["expected_quality_flag_counts"])
        self.assertEqual(
            action_summary["by_action"]["rewrite_fragment_expected_final"]["examples"][0]["id"],
            "fragment-expected",
        )
        self.assertEqual(report["strict_logic_candidate_summary"]["strict_case_count"], 0)

    def test_summarizes_evidence_strata_without_changing_scores(self) -> None:
        results = [
            {
                "language": "en",
                "tags": ["en", "missing-final", "stage-queue"],
                "expected_final": ["A sentence."],
                "actual_final": [],
                "actual_pending": "",
                "actual_staged": "A sentence.",
                "actual_staged_queue": [],
                "final_score": _score(0.0, 0.0, 0.0),
                "final_boundary_score": _score(0.0, 0.0, 0.0),
                "completed_last_score": _score(0.0, 0.0, 0.0),
                "pending_exact": False,
                "staged_exact": False,
                "case_exact_match": False,
                "metrics": {"stage_start": 1, "stage_queue_revision": 1},
            },
            {
                "language": "ko",
                "tags": ["ko", "audio-residual", "no-speech"],
                "expected_final": ["입력과 무관한 잔류 출력입니다."],
                "actual_final": ["잔류 출력입니다."],
                "actual_pending": "",
                "actual_staged": "",
                "actual_staged_queue": [],
                "final_score": _score(0.5, 0.5, 0.5),
                "final_boundary_score": _score(0.5, 0.5, 0.5),
                "completed_last_score": _score(0.5, 0.5, 0.5),
                "pending_exact": True,
                "staged_exact": True,
                "case_exact_match": False,
                "metrics": {"finalized": 1, "stage_start": 1},
            },
        ]

        summary = summarize_results_by_evidence_strata(results)

        self.assertEqual(summary["all_cases"]["case_count"], 2)
        self.assertEqual(summary["lifecycle_focus"]["case_count"], 1)
        self.assertEqual(summary["input_contamination_review"]["case_count"], 1)
        self.assertEqual(summary["lifecycle_without_input_review"]["case_count"], 1)
        self.assertEqual(summary["lifecycle_without_input_review"]["metrics"]["stage_queue_revision"], 1)

    def test_summarizes_case_exemplars_by_lifecycle_bottleneck(self) -> None:
        results = [
            {
                "id": "lifecycle-heavy",
                "language": "en",
                "tags": ["missing-final", "stage-queue"],
                "expected_final": ["Expected sentence."],
                "actual_final": [],
                "actual_pending": "",
                "actual_staged": "Expected sentence.",
                "actual_staged_queue": ["Queued sentence."],
                "final_score": _score(0.0, 0.0, 0.0),
                "final_boundary_score": _score(0.0, 0.0, 0.0),
                "completed_last_score": _score(0.0, 0.0, 0.0),
                "pending_exact": False,
                "staged_exact": False,
                "case_exact_match": False,
                "metrics": {
                    "stage_queue_revision": 7,
                    "stage_replace_deferred": 9,
                    "stage_candidate_quality_blocked": 3,
                },
            },
            {
                "id": "input-review",
                "language": "ko",
                "tags": ["audio-residual", "no-speech"],
                "expected_final": ["잔류 출력입니다."],
                "actual_final": ["잔류 출력입니다."],
                "actual_pending": "",
                "actual_staged": "",
                "actual_staged_queue": [],
                "final_score": _score(1.0, 1.0, 1.0),
                "final_boundary_score": _score(1.0, 1.0, 1.0),
                "completed_last_score": _score(1.0, 1.0, 1.0),
                "pending_exact": True,
                "staged_exact": True,
                "case_exact_match": True,
                "metrics": {"stage_queue_revision": 99, "stage_replace_deferred": 99},
            },
        ]

        summary = summarize_case_exemplars(results)

        self.assertEqual(summary["lifecycle_focus_top"][0]["id"], "lifecycle-heavy")
        self.assertEqual(summary["lifecycle_focus_top"][0]["metrics"]["stage_queue_revision"], 7)
        self.assertEqual(summary["input_contamination_review"][0]["id"], "input-review")
        self.assertIn("Expected sentence.", summary["lifecycle_focus_top"][0]["expected_final_preview"])

    def test_summarizes_staged_queue_residue_shape(self) -> None:
        results = [
            {"actual_staged_queue": [], "actual_staged": "", "actual_pending": ""},
            {
                "actual_staged_queue": ["queued one", "queued two"],
                "actual_staged": "active",
                "actual_pending": "pending",
            },
            {
                "actual_staged_queue": ["a", "b", "c", "d", "e"],
                "actual_staged": "",
                "actual_pending": "",
            },
        ]

        summary = summarize_staged_queue_residue(results)

        self.assertEqual(summary["case_count"], 3)
        self.assertEqual(summary["queue_residue_case_count"], 2)
        self.assertAlmostEqual(summary["queue_residue_case_ratio"], 2 / 3)
        self.assertEqual(summary["queue_residue_total"], 7)
        self.assertAlmostEqual(summary["queue_residue_avg_per_case"], 7 / 3)
        self.assertAlmostEqual(summary["queue_residue_avg_when_present"], 3.5)
        self.assertEqual(summary["queue_residue_max"], 5)
        self.assertEqual(summary["queue_residue_len_ge_2_count"], 2)
        self.assertEqual(summary["queue_residue_len_ge_5_count"], 1)
        self.assertEqual(summary["active_staged_residue_case_count"], 1)
        self.assertEqual(summary["pending_residue_case_count"], 1)
        self.assertEqual(summary["top_queue_residue_cases"][0]["queue_len"], 5)
        self.assertEqual(summary["top_queue_residue_cases"][0]["active_staged"], False)
        self.assertEqual(summary["top_queue_residue_cases"][1]["queue_len"], 2)
        self.assertEqual(summary["top_queue_residue_cases"][1]["pending"], True)

    def test_summarizes_top_queue_residue_cases_with_context(self) -> None:
        results = [
            {
                "id": "short-queue",
                "language": "ko",
                "tags": ["stage-queue"],
                "expected_final": ["짧은 큐입니다."],
                "actual_final": [],
                "actual_pending": "",
                "actual_staged": "",
                "actual_staged_queue": ["queued"],
                "final_score": _score(0.0, 0.0, 0.0),
                "final_boundary_score": _score(0.0, 0.0, 0.0),
                "metrics": {"stage_queue_revision": 100, "stage_replace_deferred": 100},
            },
            {
                "id": "long-queue",
                "language": "en",
                "tags": ["stage-queue", "missing-final"],
                "expected_final": ["Expected long queue sentence."],
                "actual_final": ["Actual sentence."],
                "actual_pending": "pending",
                "actual_staged": "active staged",
                "actual_staged_queue": ["queued one", "queued two", "queued three"],
                "final_score": _score(0.5, 0.5, 0.5),
                "final_boundary_score": _score(0.0, 0.0, 0.0),
                "metrics": {"stage_queue_revision": 3, "stage_replace_deferred": 4},
            },
        ]

        summary = summarize_staged_queue_residue(results)
        top = summary["top_queue_residue_cases"][0]

        self.assertEqual(top["id"], "long-queue")
        self.assertEqual(top["queue_len"], 3)
        self.assertTrue(top["active_staged"])
        self.assertTrue(top["pending"])
        self.assertEqual(top["stage_queue_revision"], 3)
        self.assertEqual(top["stage_replace_deferred"], 4)
        self.assertEqual(top["expected_final_preview"], "Expected long queue sentence.")
        self.assertEqual(top["actual_staged_queue_preview"], "queued one")

    def test_summarizes_queue_residue_severity_strata(self) -> None:
        results = [
            {
                "actual_staged_queue": [],
                "actual_staged": "",
                "actual_pending": "",
                "expected_final": ["A."],
                "actual_final": ["A."],
                "final_score": _score(1.0, 1.0, 1.0),
                "final_boundary_score": _score(1.0, 1.0, 1.0),
                "completed_last_score": _score(1.0, 1.0, 1.0),
                "pending_exact": True,
                "staged_exact": True,
                "case_exact_match": True,
                "metrics": {"stage_queue_revision": 0},
            },
            {
                "actual_staged_queue": ["one"],
                "actual_staged": "active",
                "actual_pending": "",
                "expected_final": ["B."],
                "actual_final": [],
                "final_score": _score(0.0, 0.0, 0.0),
                "final_boundary_score": _score(0.0, 0.0, 0.0),
                "completed_last_score": _score(0.0, 0.0, 0.0),
                "pending_exact": False,
                "staged_exact": False,
                "case_exact_match": False,
                "metrics": {"stage_queue_revision": 2, "stage_replace_deferred": 3},
            },
            {
                "actual_staged_queue": ["a", "b", "c"],
                "actual_staged": "",
                "actual_pending": "",
                "expected_final": ["C."],
                "actual_final": [],
                "final_score": _score(0.0, 0.0, 0.0),
                "final_boundary_score": _score(0.0, 0.0, 0.0),
                "completed_last_score": _score(0.0, 0.0, 0.0),
                "pending_exact": False,
                "staged_exact": False,
                "case_exact_match": False,
                "metrics": {"stage_queue_revision": 4, "stage_replace_deferred": 5},
            },
            {
                "actual_staged_queue": ["a", "b", "c", "d", "e"],
                "actual_staged": "",
                "actual_pending": "pending",
                "expected_final": ["D."],
                "actual_final": [],
                "final_score": _score(0.0, 0.0, 0.0),
                "final_boundary_score": _score(0.0, 0.0, 0.0),
                "completed_last_score": _score(0.0, 0.0, 0.0),
                "pending_exact": False,
                "staged_exact": False,
                "case_exact_match": False,
                "metrics": {"stage_queue_revision": 6, "stage_replace_deferred": 7},
            },
        ]

        summary = summarize_results_by_queue_residue_strata(results)

        self.assertEqual(summary["no_queue"]["case_count"], 1)
        self.assertEqual(summary["queue_len_1"]["case_count"], 1)
        self.assertEqual(summary["queue_len_2_to_4"]["case_count"], 1)
        self.assertEqual(summary["queue_len_ge_5"]["case_count"], 1)
        self.assertEqual(summary["queue_len_ge_5"]["pending_exact_match"], 0)
        self.assertEqual(summary["queue_len_ge_5"]["metrics"]["stage_queue_revision"], 6)
        self.assertEqual(summary["queue_len_ge_5"]["staged_residue_count"], 1)

    def test_summarizes_residual_metrics_by_language(self) -> None:
        results = [
            {
                "language": "ko",
                "tags": ["ko", "missing-final"],
                "expected_final": ["문장입니다."],
                "actual_final": ["문장입니다."],
                "actual_pending": "",
                "actual_staged": "",
                "actual_staged_queue": [],
                "final_score": _score(1.0, 1.0, 1.0, exact=True),
                "final_boundary_score": _score(1.0, 1.0, 1.0, exact=True),
                "completed_last_score": _score(0.5, 0.5, 0.5),
                "pending_exact": True,
                "staged_exact": True,
                "case_exact_match": True,
                "metrics": {"finalized": 2, "stage_start": 2},
            },
            {
                "language": "ko",
                "tags": ["ko", "missing-final", "stage-queue"],
                "expected_final": ["누락된 문장입니다."],
                "actual_final": [],
                "actual_pending": "누락된 문장입니다.",
                "actual_staged": "누락된 문장입니다.",
                "actual_staged_queue": ["다음 문장입니다."],
                "final_score": _score(0.0, 0.0, 0.0),
                "final_boundary_score": _score(0.0, 0.0, 0.0),
                "completed_last_score": _score(0.0, 0.0, 0.0),
                "pending_exact": False,
                "staged_exact": False,
                "case_exact_match": False,
                "metrics": {"stage_start": 1, "stage_queue_enqueue": 1},
            },
            {
                "language": "en",
                "tags": ["en", "duplicate-final"],
                "expected_final": [],
                "actual_final": [],
                "actual_pending": "",
                "actual_staged": "",
                "actual_staged_queue": [],
                "final_score": _score(1.0, 1.0, 1.0, exact=True),
                "final_boundary_score": _score(1.0, 1.0, 1.0, exact=True),
                "completed_last_score": _score(1.0, 1.0, 1.0),
                "pending_exact": True,
                "staged_exact": True,
                "case_exact_match": True,
                "metrics": {},
            },
        ]

        summary = summarize_results_by_language(results)

        self.assertEqual(set(summary), {"en", "ko"})
        self.assertEqual(summary["ko"]["case_count"], 2)
        self.assertEqual(summary["ko"]["case_exact_match"], 1)
        self.assertEqual(summary["ko"]["pending_exact_match"], 1)
        self.assertEqual(summary["ko"]["staged_exact_match"], 1)
        self.assertEqual(summary["ko"]["finalized"], 2)
        self.assertEqual(summary["ko"]["stage_start"], 3)
        self.assertAlmostEqual(summary["ko"]["finalized_per_stage_start"], 2 / 3)
        self.assertAlmostEqual(summary["ko"]["final_f1_avg"], 0.5)
        self.assertEqual(summary["ko"]["staged_residue_count"], 1)
        self.assertEqual(summary["ko"]["empty_final_count"], 1)
        self.assertEqual(summary["ko"]["expected_boundary_zero_count"], 1)
        self.assertEqual(summary["ko"]["metrics"]["stage_queue_enqueue"], 1)
        self.assertEqual(summary["en"]["empty_final_count"], 0)
        self.assertEqual(summary["en"]["expected_boundary_zero_count"], 0)

    def test_summarizes_residual_metrics_by_case_tag(self) -> None:
        results = [
            {
                "language": "ko",
                "tags": ["ko", "log-20260621", "stock-market", "missing-final"],
                "expected_final": ["누락된 문장입니다."],
                "actual_final": [],
                "actual_pending": "",
                "actual_staged": "누락된 문장입니다.",
                "actual_staged_queue": [],
                "final_score": _score(0.0, 0.0, 0.0),
                "final_boundary_score": _score(0.0, 0.0, 0.0),
                "completed_last_score": _score(0.0, 0.0, 0.0),
                "pending_exact": False,
                "staged_exact": False,
                "case_exact_match": False,
                "metrics": {"stage_start": 1},
            },
            {
                "language": "ko",
                "tags": ["ko", "war", "missing-final", "duplicate-final"],
                "expected_final": ["회수된 문장입니다."],
                "actual_final": ["회수된 문장입니다."],
                "actual_pending": "",
                "actual_staged": "",
                "actual_staged_queue": [],
                "final_score": _score(1.0, 1.0, 1.0, exact=True),
                "final_boundary_score": _score(1.0, 1.0, 1.0, exact=True),
                "completed_last_score": _score(1.0, 1.0, 1.0),
                "pending_exact": True,
                "staged_exact": True,
                "case_exact_match": True,
                "metrics": {"finalized": 1, "stage_start": 1},
            },
        ]

        summary = summarize_results_by_tag(results)

        self.assertEqual(set(summary), {"duplicate-final", "missing-final"})
        self.assertEqual(summary["missing-final"]["case_count"], 2)
        self.assertEqual(summary["missing-final"]["case_exact_match"], 1)
        self.assertAlmostEqual(summary["missing-final"]["final_f1_avg"], 0.5)
        self.assertEqual(summary["missing-final"]["empty_final_count"], 1)
        self.assertEqual(summary["missing-final"]["expected_boundary_zero_count"], 1)
        self.assertEqual(summary["duplicate-final"]["case_count"], 1)
        self.assertAlmostEqual(summary["duplicate-final"]["final_f1_avg"], 1.0)

    def test_summarizes_lifecycle_bottlenecks_for_paper_interpretation(self) -> None:
        results = [
            {
                "language": "en",
                "expected_final": ["A.", "B."],
                "actual_final": ["A.", "B.", "B."],
                "actual_pending": "",
                "actual_staged": "",
                "actual_staged_queue": ["C."],
                "metrics": {
                    "stage_replace_deferred": 2,
                    "stage_replace_decision_unconfirmed": 2,
                    "stage_queue_revision": 1,
                    "stage_candidate_quality_no_end_marker": 3,
                },
            },
            {
                "language": "ko",
                "expected_final": ["가.", "나."],
                "actual_final": [],
                "actual_pending": "가.",
                "actual_staged": "나.",
                "actual_staged_queue": [],
                "metrics": {
                    "stage_candidate_quality_blocked": 4,
                    "final_quality_no_end_marker": 1,
                    "stage_candidate_quality_short_no_end_fragment": 2,
                },
            },
        ]

        summary = summarize_lifecycle_bottlenecks(
            results,
            {
                "stage_start": 3,
                "finalized": 3,
                "stage_replace_deferred": 2,
                "stage_replace_decision_unconfirmed": 2,
                "stage_queue_revision": 1,
                "stage_candidate_quality_no_end_marker": 3,
                "final_quality_no_end_marker": 1,
                "stage_candidate_quality_blocked": 4,
                "stage_candidate_quality_short_no_end_fragment": 2,
            },
        )

        self.assertIn("stage_replace_deferred", summary["metric_keys"])
        self.assertEqual(summary["metrics"]["stage_start"], 3)
        self.assertEqual(summary["metrics"]["final_quality_no_end_marker"], 1)
        self.assertEqual(summary["replacement_decision_counts"], {"unconfirmed": 2})
        self.assertEqual(summary["deferred_replacement_decision_counts"], {"unconfirmed": 2})
        self.assertEqual(
            summary["quality_block_reason_counts"],
            {"no_end_marker": 3, "short_no_end_fragment": 2},
        )
        self.assertEqual(summary["by_language"]["en"]["overfinal_count"], 1)
        self.assertEqual(summary["by_language"]["en"]["underfinal_count"], 0)
        self.assertEqual(summary["by_language"]["en"]["staged_queue_residue_count"], 1)
        self.assertEqual(summary["by_language"]["en"]["no_end_marker_count"], 3)
        self.assertEqual(summary["by_language"]["ko"]["underfinal_count"], 1)
        self.assertEqual(summary["by_language"]["ko"]["zero_actual_final_expected_count"], 1)
        self.assertEqual(summary["by_language"]["ko"]["pending_residue_count"], 1)
        self.assertEqual(summary["by_language"]["ko"]["staged_residue_count"], 1)
        self.assertEqual(summary["by_language"]["ko"]["quality_blocked_count"], 4)
        self.assertEqual(summary["by_language"]["ko"]["no_end_marker_count"], 1)


if __name__ == "__main__":
    unittest.main()
