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
    summarize_missing_expected_without_terminal_residue,
    summarize_missing_expected_split_coverage,
    summarize_terminal_expected_residue,
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
            chunks=[
                "안녕하세요. 반갑습니다.",
                "안녕하세요. 반갑습니다.",
                "안녕하세요. 반갑습니다.",
            ],
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
                "chunks": [
                    {"input": "안녕하세요. 반갑습니다."},
                    {"input": "안녕하세요. 반갑습니다."},
                    {"input": "안녕하세요. 반갑습니다."},
                ],
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
            "tests.eval.dictation_ai.benchmark.sbd_lifecycle_state.LifecycleState",
        )
        self.assertIn(
            "staged queue promotion",
            report["lifecycle_replay_contract"]["shared_state_transitions"],
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
        self.assertEqual(strict_summary["lowest_cases"][0]["id"], "case-a")
        self.assertEqual(
            strict_summary["lowest_cases"][0]["lifecycle_metrics"],
            {"pending_overrun": 1, "pending_quality_repeated_word_ngram": 1},
        )
        self.assertEqual(report["cases"][0]["expected_quality_flags"], [])
        self.assertEqual(report["cases"][0]["case_context_flags"], [])
        self.assertEqual(report["cases"][0]["case_definition_flags"], [])
        self.assertTrue(report["cases"][0]["input_evidence"]["has_evidence"])
        self.assertTrue(report["cases"][0]["input_evidence"]["fully_supported"])
        self.assertEqual(report["cases"][0]["input_evidence"]["covered_count"], 2)
        self.assertEqual(report["case_definition_strata_summary"]["clean_case_definition"]["case_count"], 1)
        self.assertEqual(report["case_definition_strata_summary"]["case_definition_review"]["case_count"], 0)
        self.assertEqual(report["case_definition_action_summary"]["review_case_count"], 0)
        self.assertEqual(report["case_definition_health_summary"]["case_definition_review_count"], 0)
        self.assertEqual(report["case_definition_health_summary"]["strict_logic_candidate_count"], 1)
        self.assertEqual(
            report["case_definition_health_summary"]["recommendation"],
            "app-logic-tuning-subset-usable",
        )
        next_action = report["tuning_next_action_summary"]
        self.assertEqual(next_action["priority"], "collect_more_cases")
        self.assertEqual(next_action["health_recommendation"], "app-logic-tuning-subset-usable")
        self.assertEqual(next_action["strict_logic_candidate_count"], 1)
        self.assertEqual(next_action["clean_low_case_count_lt_0_65"], 0)
        source_trace = report["source_trace_strata_summary"]["strata"]
        self.assertEqual(source_trace["missing_source_trace"]["expected_final_case_count"], 1)
        self.assertEqual(source_trace["missing_source_trace"]["logic_tuning_candidate_count"], 1)
        self.assertEqual(report["case_exemplar_summary"]["lifecycle_focus_top"][0]["id"], "case-a")
        self.assertEqual(report["staged_queue_residue_summary"]["queue_residue_case_count"], 0)
        self.assertEqual(report["staged_queue_residue_summary"]["active_staged_residue_case_count"], 0)
        self.assertEqual(report["terminal_expected_residue_summary"]["case_count"], 0)
        self.assertEqual(report["missing_expected_without_terminal_residue_summary"]["case_count"], 0)
        self.assertEqual(report["missing_expected_split_coverage_summary"]["case_count"], 0)
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

    def test_single_expected_final_can_be_strict_logic_candidate(self) -> None:
        args = Namespace(
            model="sat-3l-sm",
            device="cuda",
            compute_type="float16",
            min_final_f1=0.0,
            fail_on_regression=False,
        )
        case = SbdCase(
            id="single-supported",
            language="ko",
            chunks=[
                "단일 문장입니다.",
                "단일 문장입니다.",
                "단일 문장입니다.",
            ],
            expected_completed=[],
            expected_pending="",
            expected_final=["단일 문장입니다."],
            expected_staged="",
            tags=("missing-final",),
            sentence_finalize_age=3,
        )
        results = [
            {
                "id": "single-supported",
                "language": "ko",
                "tags": ["missing-final"],
                "expected_final": ["단일 문장입니다."],
                "chunks": [
                    {"input": "단일 문장입니다."},
                    {"input": "단일 문장입니다."},
                    {"input": "단일 문장입니다."},
                ],
                "initial_final": [],
                "actual_final": [],
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

        strict_summary = report["strict_logic_candidate_summary"]
        self.assertEqual(strict_summary["strict_case_count"], 1)
        self.assertEqual(strict_summary["strict_case_ids"], ["single-supported"])
        self.assertEqual(strict_summary["actionable_low_final"]["case_count"], 1)
        self.assertEqual(
            strict_summary["actionable_low_final"]["issue_kind_counts"],
            {"underfinal_missing_no_residue": 1},
        )
        self.assertEqual(strict_summary["actionable_low_final"]["examples"][0]["id"], "single-supported")
        self.assertEqual(
            strict_summary["actionable_low_final"]["examples"][0]["issue_kind"],
            "underfinal_missing_no_residue",
        )
        self.assertEqual(
            strict_summary["actionable_low_final"]["metric_presence"]["stage_candidate_quality_blocked"]["case_count"],
            1,
        )
        self.assertEqual(strict_summary["metric_presence"]["stage_candidate_quality_blocked"]["case_count"], 1)
        self.assertEqual(strict_summary["lowest_cases"][0]["id"], "single-supported")
        self.assertEqual(
            report["clean_low_bottleneck_intersection_summary"]["thresholds"]["0.35"]["case_count"],
            1,
        )
        self.assertEqual(
            report["supported_low_bottleneck_intersection_summary"]["thresholds"]["0.35"]["case_count"],
            1,
        )

    def test_report_summarizes_expected_final_left_as_terminal_residue(self) -> None:
        result = {
            "id": "case-terminal-residue",
            "language": "ko",
            "tags": ["missing-final", "stage-queue"],
            "expected_final": ["첫 문장입니다.", "남은 문장입니다."],
            "actual_final": ["첫 문장입니다."],
            "actual_pending": "",
            "actual_staged": "남은 문장입니다.",
            "actual_staged_queue": [],
            "final_score": _score(1.0, 0.5, 0.6666666666666666),
            "final_boundary_score": _score(1.0, 0.5, 0.6666666666666666),
            "metrics": {
                "stage_age_quality_blocked": 1,
                "stage_queue_promote": 2,
                "stage_revision_token_sentence_deferred": 1,
            },
        }

        summary = summarize_terminal_expected_residue([result])

        self.assertEqual(summary["case_count"], 1)
        self.assertEqual(summary["matched_missing_expected_total"], 1)
        top = summary["top_cases"][0]
        self.assertEqual(top["id"], "case-terminal-residue")
        self.assertEqual(top["expected_final_count"], 2)
        self.assertEqual(top["actual_final_count"], 1)
        self.assertEqual(top["terminal_residue_count"], 1)
        self.assertEqual(top["matched_missing_expected_count"], 1)
        self.assertEqual(top["stage_age_quality_blocked"], 1)
        self.assertEqual(top["stage_queue_promote"], 2)
        self.assertEqual(top["stage_revision_token_sentence_deferred"], 1)
        self.assertEqual(top["expected_residue_matches"][0]["expected"], "남은 문장입니다.")

    def test_report_summarizes_expected_final_missing_without_terminal_residue(self) -> None:
        result = {
            "id": "case-missing-without-residue",
            "language": "ko",
            "tags": ["missing-final", "stage-queue"],
            "expected_final": ["첫 문장입니다.", "소실된 문장입니다."],
            "actual_final": ["첫 문장입니다."],
            "actual_pending": "",
            "actual_staged": "다른 후보입니다.",
            "actual_staged_queue": [],
            "final_score": _score(1.0, 0.5, 0.6666666666666666),
            "final_boundary_score": _score(1.0, 0.5, 0.6666666666666666),
            "metrics": {
                "stage_age_quality_blocked": 2,
                "stage_candidate_quality_blocked": 1,
                "stage_queue_promote": 3,
                "stage_revision_token_sentence_deferred": 1,
                "candidate_delta_trimmed": 4,
                "candidate_recent_final_delta_trimmed": 2,
            },
        }

        summary = summarize_missing_expected_without_terminal_residue([result])

        self.assertEqual(summary["case_count"], 1)
        self.assertEqual(summary["missing_expected_total"], 1)
        self.assertEqual(
            summary["metric_totals"],
            {
                "stage_age_quality_blocked": 2,
                "stage_candidate_quality_blocked": 1,
                "stage_queue_promote": 3,
                "stage_revision_token_sentence_deferred": 1,
                "candidate_delta_trimmed": 4,
                "candidate_recent_final_delta_trimmed": 2,
            },
        )
        top = summary["top_cases"][0]
        self.assertEqual(top["id"], "case-missing-without-residue")
        self.assertEqual(top["missing_expected_count"], 1)
        self.assertEqual(top["missing_expected"][0]["expected"], "소실된 문장입니다.")

    def test_report_summarizes_missing_expected_covered_by_split_output(self) -> None:
        result = {
            "id": "case-split-covered",
            "language": "ko",
            "tags": ["missing-final", "stage-queue"],
            "expected_final": ["긴 문장이 앞부분과 가운데 내용과 뒷부분으로 나뉘어서 출력됩니다."],
            "actual_final": ["긴 문장이 앞부분과"],
            "actual_pending": "",
            "actual_staged": "가운데 내용과",
            "actual_staged_queue": ["뒷부분으로 나뉘어서 출력됩니다."],
            "final_score": _score(0.0, 0.0, 0.0),
            "final_boundary_score": _score(0.0, 0.0, 0.0),
            "metrics": {"stage_age_quality_blocked": 1},
        }

        summary = summarize_missing_expected_split_coverage([result])

        self.assertEqual(summary["case_count"], 1)
        self.assertEqual(summary["split_coverage_total"], 1)
        top = summary["top_cases"][0]
        self.assertEqual(top["id"], "case-split-covered")
        self.assertEqual(top["split_coverage_count"], 1)
        self.assertEqual(top["split_coverage_matches"][0]["expected"], "긴 문장이 앞부분과 가운데 내용과 뒷부분으로 나뉘어서 출력됩니다.")
        self.assertEqual(top["split_coverage_matches"][0]["combined_total_coverage"], 1.0)

    def test_split_coverage_case_is_boundary_review_not_strict_logic_candidate(self) -> None:
        args = Namespace(
            model="sat-3l-sm",
            device="cuda",
            compute_type="float16",
            min_final_f1=0.0,
            fail_on_regression=False,
        )
        case = SbdCase(
            id="case-split-covered",
            language="ko",
            chunks=[
                "긴 문장이 앞부분과 가운데 내용과 뒷부분으로 나뉘어서 출력됩니다.",
                "긴 문장이 앞부분과 가운데 내용과 뒷부분으로 나뉘어서 출력됩니다.",
                "긴 문장이 앞부분과 가운데 내용과 뒷부분으로 나뉘어서 출력됩니다.",
            ],
            expected_completed=[],
            expected_pending="",
            expected_final=["긴 문장이 앞부분과 가운데 내용과 뒷부분으로 나뉘어서 출력됩니다."],
            expected_staged="",
            tags=("missing-final",),
            sentence_finalize_age=3,
        )
        results = [
            {
                "id": "case-split-covered",
                "language": "ko",
                "tags": ["missing-final"],
                "expected_final": case.expected_final,
                "chunks": [{"input": chunk} for chunk in case.chunks],
                "initial_final": [],
                "actual_final": ["긴 문장이 앞부분과"],
                "actual_pending": "",
                "actual_staged": "가운데 내용과",
                "actual_staged_queue": ["뒷부분으로 나뉘어서 출력됩니다."],
                "final_score": _score(0.0, 0.0, 0.0),
                "final_ordered_score": _score(0.0, 0.0, 0.0),
                "final_boundary_score": _score(0.0, 0.0, 0.0),
                "completed_last_score": _score(0.0, 0.0, 0.0),
                "pending_exact": True,
                "staged_exact": False,
                "case_exact_match": False,
                "metrics": {"stage_age_quality_blocked": 1},
            }
        ]

        report = build_benchmark_report(
            args=args,
            case_sources=["cases.jsonl"],
            corpus_role="challenge-replay",
            cases=[case],
            results=results,
            metric_totals={"stage_age_quality_blocked": 1},
            elapsed_ms=1.0,
        )

        self.assertEqual(
            report["case_definition_action_summary"]["action_counts"],
            {"manual_boundary_review": 1},
        )
        self.assertEqual(report["strict_logic_candidate_summary"]["strict_case_count"], 0)

    def test_actual_final_supported_by_omitted_stable_candidate_is_definition_review(self) -> None:
        args = Namespace(
            model="sat-3l-sm",
            device="cuda",
            compute_type="float16",
            min_final_f1=0.0,
            fail_on_regression=False,
        )
        case = SbdCase(
            id="omitted-stable-actual",
            language="ko",
            chunks=[
                "첫 번째 문장입니다.",
                "첫 번째 문장입니다. 두 번째 안정 후보입니다.",
                "첫 번째 문장입니다. 두 번째 안정 후보입니다.",
                "두 번째 안정 후보입니다.",
            ],
            expected_completed=[],
            expected_pending="",
            expected_final=["첫 번째 문장입니다."],
            expected_staged="",
            tags=("missing-final",),
            sentence_finalize_age=3,
        )
        results = [
            {
                "id": case.id,
                "language": case.language,
                "tags": list(case.tags),
                "expected_final": case.expected_final,
                "chunks": [{"input": chunk} for chunk in case.chunks],
                "initial_final": [],
                "actual_final": ["첫 번째 문장입니다.", "두 번째 안정 후보입니다"],
                "actual_pending": "",
                "actual_staged": "",
                "actual_staged_queue": [],
                "final_score": _score(0.5, 1.0, 0.6666666667),
                "final_ordered_score": _score(0.5, 1.0, 0.6666666667),
                "final_boundary_score": _score(0.5, 1.0, 0.6666666667),
                "completed_last_score": _score(0.0, 0.0, 0.0),
                "pending_exact": True,
                "staged_exact": True,
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

        self.assertEqual(
            report["cases"][0]["case_definition_flags"],
            ["expected_final_omits_stable_actual_sentence"],
        )
        self.assertEqual(
            report["case_definition_action_summary"]["action_counts"],
            {"manual_boundary_review": 1},
        )
        self.assertEqual(report["strict_logic_candidate_summary"]["strict_case_count"], 0)

    def test_omitted_stable_candidate_embedded_in_long_actual_is_not_definition_review(self) -> None:
        args = Namespace(
            model="sat-3l-sm",
            device="cuda",
            compute_type="float16",
            min_final_f1=0.0,
            fail_on_regression=False,
        )
        case = SbdCase(
            id="embedded-stable-actual",
            language="ko",
            chunks=[
                "첫 번째 문장입니다.",
                "첫 번째 문장입니다. 근데 이제 다음은 이런.",
                "근데 이제 다음은 이런.",
                "근데 이제 다음은 이런. 오염된 이전 문장이 다시 섞였습니다.",
            ],
            expected_completed=[],
            expected_pending="",
            expected_final=["첫 번째 문장입니다."],
            expected_staged="",
            tags=("duplicate-final",),
            sentence_finalize_age=3,
        )
        results = [
            {
                "id": case.id,
                "language": case.language,
                "tags": list(case.tags),
                "expected_final": case.expected_final,
                "chunks": [{"input": chunk} for chunk in case.chunks],
                "initial_final": [],
                "actual_final": [
                    "첫 번째 문장입니다.",
                    "근데 이제 다음은 이런. 오염된 이전 문장이 다시 섞였습니다.",
                ],
                "actual_pending": "",
                "actual_staged": "",
                "actual_staged_queue": [],
                "final_score": _score(0.5, 1.0, 0.6666666667),
                "final_ordered_score": _score(0.5, 1.0, 0.6666666667),
                "final_boundary_score": _score(0.5, 1.0, 0.6666666667),
                "completed_last_score": _score(0.0, 0.0, 0.0),
                "pending_exact": True,
                "staged_exact": True,
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

        self.assertEqual(report["cases"][0]["case_definition_flags"], [])
        self.assertEqual(
            report["case_definition_action_summary"]["action_counts"],
            {"recut_or_relabel_stable_candidate_mismatch": 1},
        )

    def test_report_marks_boundary_zero_high_final_as_metric_sensitivity(self) -> None:
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
            chunks=["문장입니다."],
            expected_completed=[],
            expected_pending="",
            expected_final=["문장입니다."],
            expected_staged="",
            tags=("missing-final",),
            sentence_finalize_age=3,
        )
        results = [
            {
                "id": "case-a",
                "language": "ko",
                "tags": ["missing-final"],
                "expected_final": ["문장입니다."],
                "chunks": [{"input": "문장입니다."}],
                "actual_final": ["문장입니다"],
                "actual_pending": "",
                "actual_staged": "",
                "actual_staged_queue": [],
                "final_score": _score(1.0, 1.0, 1.0),
                "final_ordered_score": _score(1.0, 1.0, 1.0),
                "final_boundary_score": _score(0.0, 0.0, 0.0),
                "completed_last_score": _score(1.0, 1.0, 1.0),
                "pending_exact": True,
                "staged_exact": True,
                "case_exact_match": False,
                "metrics": {"finalized": 1, "stage_start": 1},
            }
        ]

        report = build_benchmark_report(
            args=args,
            case_sources=["cases.jsonl"],
            corpus_role="challenge-replay",
            cases=[case],
            results=results,
            metric_totals={"finalized": 1, "stage_start": 1},
            elapsed_ms=1.0,
        )

        summary = report["boundary_zero_high_final_summary"]
        self.assertEqual(summary["expected_case_count"], 1)
        self.assertEqual(summary["boundary_zero_high_final_count"], 1)
        self.assertEqual(summary["boundary_zero_high_ordered_count"], 1)
        self.assertEqual(summary["boundary_zero_high_final_examples"][0]["id"], "case-a")

    def test_report_marks_high_recall_oversegmentation_as_boundary_granularity(self) -> None:
        args = Namespace(
            model="sat-3l-sm",
            device="cuda",
            compute_type="float16",
            min_final_f1=0.0,
            fail_on_regression=False,
        )
        case = SbdCase(
            id="case-split",
            language="zh",
            chunks=["第一句。第二句。第三句前半。第三句后半。第四句。"],
            expected_completed=[],
            expected_pending="",
            expected_final=["第一句。", "第二句。", "第三句前半第三句后半。", "第四句。"],
            expected_staged="",
            tags=("missing-final",),
            sentence_finalize_age=3,
        )
        results = [
            {
                "id": "case-split",
                "language": "zh",
                "tags": ["missing-final"],
                "expected_final": ["第一句。", "第二句。", "第三句前半第三句后半。", "第四句。"],
                "chunks": [{"input": "第一句。第二句。第三句前半。第三句后半。第四句。"}],
                "actual_final": ["第一句。", "第二句。", "第三句前半。", "第三句后半。", "第四句。"],
                "actual_pending": "",
                "actual_staged": "",
                "actual_staged_queue": [],
                "final_score": _score(0.8, 1.0, 0.888888888888889),
                "final_ordered_score": _score(0.8, 1.0, 0.888888888888889),
                "final_boundary_score": _score(0.2, 0.25, 0.22222222222222224),
                "completed_last_score": _score(1.0, 1.0, 1.0),
                "pending_exact": True,
                "staged_exact": True,
                "case_exact_match": False,
                "metrics": {"finalized": 3, "stage_start": 3},
            }
        ]

        report = build_benchmark_report(
            args=args,
            case_sources=["cases.jsonl"],
            corpus_role="challenge-replay",
            cases=[case],
            results=results,
            metric_totals={"finalized": 3, "stage_start": 3},
            elapsed_ms=1.0,
        )

        summary = report["boundary_granularity_summary"]
        self.assertEqual(summary["expected_case_count"], 1)
        self.assertEqual(summary["boundary_granularity_case_count"], 1)
        example = summary["boundary_granularity_examples"][0]
        self.assertEqual(example["id"], "case-split")
        self.assertEqual(example["expected_final_count"], 4)
        self.assertEqual(example["actual_final_count"], 5)
        self.assertEqual(report["case_definition_action_summary"]["action_counts"], {"manual_boundary_review": 1})
        self.assertEqual(report["strict_logic_candidate_summary"]["strict_case_count"], 0)

    def test_strict_summary_separates_boundary_metric_sensitivity(self) -> None:
        args = Namespace(
            model="sat-3l-sm",
            device="cuda",
            compute_type="float16",
            min_final_f1=0.0,
            fail_on_regression=False,
        )
        case = SbdCase(
            id="case-boundary-sensitive",
            language="ko",
            chunks=[
                "실제 문장입니다.",
                "실제 문장입니다.",
                "실제 문장입니다.",
            ],
            expected_completed=[],
            expected_pending="",
            expected_final=["실제 문장입니다."],
            expected_staged="",
            tags=("missing-final",),
            sentence_finalize_age=3,
        )
        results = [
            {
                "id": "case-boundary-sensitive",
                "language": "ko",
                "tags": ["missing-final"],
                "expected_final": ["실제 문장입니다."],
                "chunks": [
                    {"input": "실제 문장입니다."},
                    {"input": "실제 문장입니다."},
                    {"input": "실제 문장입니다."},
                ],
                "actual_final": ["앞부분 실제 문장입니다."],
                "actual_pending": "",
                "actual_staged": "",
                "actual_staged_queue": [],
                "final_score": _score(1.0, 1.0, 1.0),
                "final_ordered_score": _score(1.0, 1.0, 1.0),
                "final_boundary_score": _score(0.0, 0.0, 0.0),
                "completed_last_score": _score(1.0, 1.0, 1.0),
                "pending_exact": True,
                "staged_exact": True,
                "case_exact_match": False,
                "metrics": {"finalized": 1, "stage_start": 1},
                "expected_quality_flags": [],
                "input_evidence": {
                    "fully_supported": True,
                    "stable_repeat_fully_supported": True,
                },
                "case_context_flags": [],
                "case_definition_flags": [],
            }
        ]

        report = build_benchmark_report(
            args=args,
            case_sources=["cases.jsonl"],
            corpus_role="challenge-replay",
            cases=[case],
            results=results,
            metric_totals={"finalized": 1, "stage_start": 1},
            elapsed_ms=1.0,
        )

        strict_summary = report["strict_logic_candidate_summary"]
        self.assertEqual(strict_summary["strict_case_count"], 1)
        sensitivity = strict_summary["boundary_metric_sensitivity"]
        self.assertEqual(sensitivity["case_count"], 1)
        self.assertEqual(sensitivity["boundary_shift_kind_counts"], {"actual_contains_expected": 1})
        self.assertEqual(sensitivity["examples"][0]["id"], "case-boundary-sensitive")
        self.assertEqual(sensitivity["examples"][0]["boundary_shift_kind"], "actual_contains_expected")
        self.assertEqual(strict_summary["actionable_low_final"]["case_count"], 0)

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
        self.assertEqual(clean_low["case_count"], 0)
        self.assertEqual(clean_low["lowest_cases"], [])
        self.assertEqual(
            report["cases"][2]["case_context_flags"],
            ["unmodeled_prefix_context"],
        )
        self.assertEqual(report["strict_logic_candidate_summary"]["strict_case_count"], 0)
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

    def test_report_flags_expected_final_that_omits_stable_actual_sentence(self) -> None:
        args = Namespace(
            model="sat-3l-sm",
            device="cuda",
            compute_type="float16",
            min_final_f1=0.0,
            fail_on_regression=False,
        )
        case = SbdCase(
            id="case-omitted-actual",
            language="zh",
            chunks=[
                "第一句到了。遗漏但完整的一句。第二句也到了。",
                "第一句到了。遗漏但完整的一句。第二句也到了。",
                "第一句到了。遗漏但完整的一句。第二句也到了。",
            ],
            expected_completed=[],
            expected_pending="",
            expected_final=["第一句到了。", "第二句也到了。"],
            expected_staged="",
            tags=("missing-final",),
            sentence_finalize_age=3,
        )
        results = [
            {
                "id": "case-omitted-actual",
                "language": "zh",
                "tags": ["missing-final"],
                "expected_final": ["第一句到了。", "第二句也到了。"],
                "chunks": [
                    {"input": "第一句到了。遗漏但完整的一句。第二句也到了。"},
                    {"input": "第一句到了。遗漏但完整的一句。第二句也到了。"},
                    {"input": "第一句到了。遗漏但完整的一句。第二句也到了。"},
                ],
                "actual_final": ["第一句到了。", "遗漏但完整的一句。", "第二句也到了。"],
                "actual_pending": "",
                "actual_staged": "",
                "actual_staged_queue": [],
                "final_score": _score(0.5, 0.5, 0.5),
                "final_ordered_score": _score(0.5, 0.5, 0.5),
                "final_boundary_score": _score(0.5, 0.5, 0.5),
                "completed_last_score": _score(0.5, 0.5, 0.5),
                "pending_exact": True,
                "staged_exact": True,
                "case_exact_match": False,
                "metrics": {"finalized": 3, "stage_start": 3},
            }
        ]

        report = build_benchmark_report(
            args=args,
            case_sources=["cases.jsonl"],
            corpus_role="challenge-replay",
            cases=[case],
            results=results,
            metric_totals={"finalized": 3, "stage_start": 3},
            elapsed_ms=1.0,
        )

        self.assertEqual(
            report["cases"][0]["case_definition_flags"],
            ["expected_final_omits_stable_actual_sentence"],
        )
        self.assertEqual(report["case_definition_action_summary"]["review_case_count"], 1)
        self.assertEqual(report["case_definition_action_summary"]["action_counts"], {"manual_boundary_review": 1})
        self.assertEqual(report["strict_logic_candidate_summary"]["strict_case_count"], 0)

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
                "The first expected sentence appears. The second expected sentence appears too.",
                "The first expected sentence appears. The second expected sentence appears too.",
                "The first expected sentence appears. The second expected sentence appears too.",
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
                "case_metadata": {"case_file": "cases/en-a.jsonl", "case_line": 1},
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
                "case_metadata": {"case_file": "cases/en-a.jsonl", "case_line": 2},
                "expected_final": [
                    "The first expected sentence appears.",
                    "The second expected sentence appears too.",
                ],
                "chunks": [
                    {
                        "input": "The first expected sentence appears. The second expected sentence appears too."
                    },
                    {
                        "input": "The first expected sentence appears. The second expected sentence appears too."
                    },
                    {
                        "input": "The first expected sentence appears. The second expected sentence appears too."
                    },
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
        health = report["case_definition_health_summary"]
        self.assertEqual(health["expected_final_case_count"], 2)
        self.assertEqual(health["case_definition_review_count"], 1)
        self.assertEqual(health["case_definition_cleanup_count"], 1)
        self.assertEqual(health["case_interpretation_review_count"], 0)
        self.assertEqual(health["logic_tuning_candidate_count"], 1)
        self.assertEqual(health["strict_logic_candidate_count"], 1)
        self.assertEqual(health["recommendation"], "prioritize-case-definition-cleanup")
        self.assertEqual(
            health["top_review_actions"],
            [{"action": "remove_or_recut_expected_outside_replay_input", "case_count": 1}],
        )
        self.assertEqual(
            report["case_definition_action_summary"]["action_counts"],
            {"remove_or_recut_expected_outside_replay_input": 1},
        )
        self.assertEqual(
            report["case_definition_action_summary"]["by_action"][
                "remove_or_recut_expected_outside_replay_input"
            ]["examples"][0]["id"],
            "partial-input-low",
        )
        file_summary = report["case_definition_file_summary"]
        self.assertEqual(file_summary["file_count"], 1)
        self.assertEqual(file_summary["files_with_review_cases"], 1)
        self.assertEqual(file_summary["top_files"][0]["case_file"], "cases/en-a.jsonl")
        self.assertEqual(file_summary["top_files"][0]["case_count"], 2)
        self.assertEqual(file_summary["top_files"][0]["review_case_count"], 1)
        self.assertEqual(file_summary["top_files"][0]["logic_tuning_candidate_count"], 1)
        self.assertEqual(
            file_summary["top_files"][0]["action_counts"],
            {"remove_or_recut_expected_outside_replay_input": 1},
        )
        self.assertEqual(file_summary["top_files"][0]["examples"][0]["id"], "partial-input-low")

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
            {"add_initial_final_or_recut_mid_stream_case": 1},
        )
        self.assertEqual(
            report["case_definition_action_summary"]["by_action"][
                "add_initial_final_or_recut_mid_stream_case"
            ]["examples"][0]["id"],
            "prefix-context-case",
        )
        self.assertEqual(report["strict_logic_candidate_summary"]["strict_case_count"], 0)

    def test_actual_prefix_before_expected_final_is_mid_stream_review(self) -> None:
        args = Namespace(
            model="sat-3l-sm",
            device="cuda",
            compute_type="float16",
            min_final_f1=0.0,
            fail_on_regression=False,
        )
        case = SbdCase(
            id="actual-prefix-case",
            language="ko",
            chunks=["목표 문장이 도착했습니다.", "목표 문장이 도착했습니다. 다음 문장입니다."],
            expected_completed=[],
            expected_pending="",
            expected_final=["목표 문장이 도착했습니다.", "다음 문장입니다."],
            expected_staged="",
            tags=("missing-final",),
            sentence_finalize_age=3,
        )
        results = [
            {
                "id": "actual-prefix-case",
                "language": "ko",
                "tags": ["missing-final"],
                "expected_final": ["목표 문장이 도착했습니다.", "다음 문장입니다."],
                "chunks": [
                    {"input": "목표 문장이 도착했습니다."},
                    {"input": "목표 문장이 도착했습니다. 다음 문장입니다."},
                ],
                "initial_final": [],
                "actual_final": ["앞 문장이 이미 끝났습니다.", "목표 문장이 도착했습니다."],
                "actual_pending": "",
                "actual_staged": "다음 문장입니다.",
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

        self.assertEqual(report["cases"][0]["case_context_flags"], ["actual_prefix_before_expected_final"])
        self.assertEqual(
            report["case_definition_action_summary"]["action_counts"],
            {"add_initial_final_or_recut_mid_stream_case": 1},
        )
        self.assertEqual(report["strict_logic_candidate_summary"]["strict_case_count"], 0)

    def test_legacy_sample_without_source_trace_is_review_action(self) -> None:
        args = Namespace(
            model="sat-3l-sm",
            device="cuda",
            compute_type="float16",
            min_final_f1=0.0,
            fail_on_regression=False,
        )
        case = SbdCase(
            id="legacy-sample-case",
            language="ko",
            chunks=["추적 가능한 문장입니다."],
            expected_completed=[],
            expected_pending="",
            expected_final=["추적 가능한 문장입니다."],
            expected_staged="",
            tags=("missing-final",),
            metadata={
                "case_file": "cases/ko-a.jsonl",
                "case_line": 1,
                "source_log": "",
                "source_chunk": None,
                "review_source_file": "tests/eval/dictation_ai/sbd_text_cases.sample.jsonl",
            },
            sentence_finalize_age=3,
        )
        results = [
            {
                "id": "legacy-sample-case",
                "language": "ko",
                "tags": ["missing-final"],
                "case_metadata": dict(case.metadata or {}),
                "expected_final": ["추적 가능한 문장입니다."],
                "chunks": [{"input": "추적 가능한 문장입니다."}],
                "actual_final": ["추적 가능한 문장입니다."],
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
                "metrics": {"stage_start": 1, "finalized": 1},
            }
        ]

        report = build_benchmark_report(
            args=args,
            case_sources=["cases.jsonl"],
            corpus_role="challenge-replay",
            cases=[case],
            results=results,
            metric_totals={"stage_start": 1, "finalized": 1},
            elapsed_ms=1.0,
        )

        self.assertEqual(report["cases"][0]["case_definition_flags"], ["legacy_sample_without_source_trace"])
        self.assertEqual(
            report["case_definition_action_summary"]["action_counts"],
            {"restore_source_log_or_recut_from_observed_log": 1},
        )
        self.assertEqual(report["case_definition_health_summary"]["strict_logic_candidate_count"], 0)
        self.assertEqual(
            report["case_definition_health_summary"]["recommendation"],
            "case-definition-review-required",
        )
        source_trace = report["source_trace_strata_summary"]["strata"]
        self.assertEqual(source_trace["legacy_sample_without_source_trace"]["expected_final_case_count"], 1)
        self.assertEqual(source_trace["legacy_sample_without_source_trace"]["review_case_count"], 1)
        self.assertEqual(
            source_trace["legacy_sample_without_source_trace"]["examples"][0]["primary_action"],
            "restore_source_log_or_recut_from_observed_log",
        )

    def test_context_strata_flags_fuzzy_unmodeled_prefix_context(self) -> None:
        args = Namespace(
            model="sat-3l-sm",
            device="cuda",
            compute_type="float16",
            min_final_f1=0.0,
            fail_on_regression=False,
        )
        case = SbdCase(
            id="fuzzy-prefix-context",
            language="ko",
            chunks=[
                "앞 문장이 이미 끝났습니다. 그러다 보니까 지금 테슬라를 포함해서 전세계 자율주행이 다 요 방향으로 가는 거고 이걸 베꼈다고 얘기할 수는 없어요",
            ],
            expected_completed=[],
            expected_pending="",
            expected_final=[
                "지금 테슬라를 포함해서 전세계 자율주행이 다 이 방향으로 가는 거고 이걸 베꼈다고 얘기할 수는 없어요."
            ],
            expected_staged="",
            tags=("missing-final",),
            sentence_finalize_age=3,
        )
        results = [
            {
                "id": "fuzzy-prefix-context",
                "language": "ko",
                "tags": ["missing-final"],
                "expected_final": [
                    "지금 테슬라를 포함해서 전세계 자율주행이 다 이 방향으로 가는 거고 이걸 베꼈다고 얘기할 수는 없어요."
                ],
                "chunks": [
                    {
                        "input": "앞 문장이 이미 끝났습니다. 그러다 보니까 지금 테슬라를 포함해서 전세계 자율주행이 다 요 방향으로 가는 거고 이걸 베꼈다고 얘기할 수는 없어요"
                    },
                ],
                "initial_final": [],
                "actual_final": [],
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

        self.assertEqual(report["cases"][0]["case_context_flags"], ["unmodeled_prefix_context"])
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
            {"deduplicate_or_justify_shifted_window_repeat": 2},
        )
        self.assertEqual(report["strict_logic_candidate_summary"]["strict_case_count"], 0)
        clean_low = report["clean_low_bottleneck_intersection_summary"]["thresholds"]["0.35"]
        self.assertEqual(clean_low["case_count"], 0)

    def test_revision_variant_expected_sentences_are_case_definition_review(self) -> None:
        args = Namespace(
            model="sat-3l-sm",
            device="cuda",
            compute_type="float16",
            min_final_f1=0.0,
            fail_on_regression=False,
        )
        case = SbdCase(
            id="revision-variant-expected",
            language="zh",
            chunks=[
                "这个自制的萝卜，然后大家几个人搅拌他们的泡面。",
                "然后大家就有人搅拌他们的泡面。",
                "这个自制的萝卜，然后大家几个人搅拌他们的泡面。",
                "然后大家就有人搅拌他们的泡面。",
                "这个自制的萝卜，然后大家几个人搅拌他们的泡面。",
                "然后大家就有人搅拌他们的泡面。",
            ],
            expected_completed=[],
            expected_pending="",
            expected_final=[
                "这个自制的萝卜，然后大家几个人搅拌他们的泡面。",
                "然后大家就有人搅拌他们的泡面。",
            ],
            expected_staged="",
            tags=("missing-final",),
            sentence_finalize_age=3,
        )
        results = [
            {
                "id": "revision-variant-expected",
                "language": "zh",
                "tags": ["missing-final"],
                "expected_final": [
                    "这个自制的萝卜，然后大家几个人搅拌他们的泡面。",
                    "然后大家就有人搅拌他们的泡面。",
                ],
                "chunks": [{"input": chunk} for chunk in case.chunks],
                "actual_final": ["这个自制的萝卜，然后大家几个人搅拌他们的泡面。"],
                "actual_pending": "",
                "actual_staged": "",
                "actual_staged_queue": [],
                "final_score": _score(1.0, 0.5, 0.6666666667),
                "final_ordered_score": _score(1.0, 0.5, 0.6666666667),
                "final_boundary_score": _score(1.0, 0.5, 0.6666666667),
                "completed_last_score": _score(1.0, 0.5, 0.6666666667),
                "pending_exact": True,
                "staged_exact": True,
                "case_exact_match": False,
                "metrics": {"finalized": 1, "stage_start": 1},
            }
        ]

        report = build_benchmark_report(
            args=args,
            case_sources=["cases.jsonl"],
            corpus_role="challenge-replay",
            cases=[case],
            results=results,
            metric_totals={"finalized": 1, "stage_start": 1},
            elapsed_ms=1.0,
        )

        self.assertEqual(report["cases"][0]["case_definition_flags"], ["expected_revision_variant_group"])
        self.assertEqual(
            report["case_definition_action_summary"]["action_counts"],
            {"rewrite_expected_final_to_final_sentence_boundary": 1},
        )
        self.assertEqual(report["strict_logic_candidate_summary"]["strict_case_count"], 0)

    def test_contained_token_expected_sentences_are_case_definition_review(self) -> None:
        args = Namespace(
            model="sat-3l-sm",
            device="cuda",
            compute_type="float16",
            min_final_f1=0.0,
            fail_on_regression=False,
        )
        case = SbdCase(
            id="contained-token-expected",
            language="ko",
            chunks=[
                "있을 것 같고 그래서 이런 쪽에 대해서는 정부나 아니면 이런 산업의 협회 혹은 학계에서도 좀 열심히 더 적극 참여를 해서 이 기반을 한번 더 만들어 줄 필요가 있다고 생각합니다.",
                "그래서 이런 쪽에 대해서는 정부나 아니면 이런 산업의 협회 혹은 학계에서도 좀 열심히 더 적극 참여를 해서 이 기반을 한 번 더 만들어 줄 필요가 있다고 생각합니다.",
                "쪽에 대해서는 정부나 아니면 이런 산업의 협회 혹은 학계에서도 좀 열심히 더 적극 참여를 해서 이 기반을 한번 더 만들어 줄 필요가 있다고 생각합니다.",
                "산업협회 혹은 학계에서도 좀 열심히 더 적극 참여를 해서 이 기반을 한 번 더 만들어 줄 필요가 있다고 생각합니다.",
                "혹은 학계에서도 좀 열심히 더 적극 참여를 해서 이 기반을 한 번 더 만들어 줄 필요가 있다고 생각합니다.",
                "열심히 더 적극 참여를 해서 이 기반을 한번 더 만들어 줄 필요가 있다고 생각합니다.",
            ],
            expected_completed=[],
            expected_pending="",
            expected_final=[
                "있을 것 같고 그래서 이런 쪽에 대해서는 정부나 아니면 이런 산업의 협회 혹은 학계에서도 좀 열심히 더 적극 참여를 해서 이 기반을 한번 더 만들어 줄 필요가 있다고 생각합니다.",
                "산업협회 혹은 학계에서도 좀 열심히 더 적극 참여를 해서 이 기반을 한 번 더 만들어 줄 필요가 있다고 생각합니다.",
            ],
            expected_staged="",
            tags=("missing-final",),
            sentence_finalize_age=3,
        )
        results = [
            {
                "id": "contained-token-expected",
                "language": "ko",
                "tags": ["missing-final"],
                "expected_final": case.expected_final,
                "chunks": [{"input": chunk} for chunk in case.chunks],
                "actual_final": [
                    "있을 것 같고 그래서 이런 쪽에 대해서는 정부나 아니면 이런 산업의 협회 혹은 학계에서도 좀 열심히 더 적극 참여를 해서 이 기반을 한번 더 만들어 줄 필요가 있다고 생각합니다."
                ],
                "actual_pending": "",
                "actual_staged": "",
                "actual_staged_queue": [],
                "final_score": _score(1.0, 0.5, 0.6666666667),
                "final_ordered_score": _score(1.0, 0.5, 0.6666666667),
                "final_boundary_score": _score(1.0, 0.5, 0.6666666667),
                "completed_last_score": _score(1.0, 0.5, 0.6666666667),
                "pending_exact": True,
                "staged_exact": True,
                "case_exact_match": False,
                "metrics": {"finalized": 1, "stage_start": 1},
            }
        ]

        report = build_benchmark_report(
            args=args,
            case_sources=["cases.jsonl"],
            corpus_role="challenge-replay",
            cases=[case],
            results=results,
            metric_totals={"finalized": 1, "stage_start": 1},
            elapsed_ms=1.0,
        )

        self.assertEqual(report["cases"][0]["case_definition_flags"], ["contained_expected_token_sentence"])
        self.assertEqual(
            report["case_definition_action_summary"]["action_counts"],
            {"rewrite_expected_final_to_final_sentence_boundary": 1},
        )
        self.assertEqual(report["strict_logic_candidate_summary"]["strict_case_count"], 0)

    def test_short_contained_token_expected_sentences_are_case_definition_review(self) -> None:
        args = Namespace(
            model="sat-3l-sm",
            device="cuda",
            compute_type="float16",
            min_final_f1=0.0,
            fail_on_regression=False,
        )
        case = SbdCase(
            id="short-contained-token-expected",
            language="ko",
            chunks=[
                "정부도 라는 좀 이런 태세의 전환도 필요하고 정부도 적극적으로 나서야 합니다.",
                "이거를 우리가 끌고 가겠다 라는 좀 이런 태세의 전환도 필요하고 정부도 적극적으로 나서야 합니다.",
                "우리가 끌고 가겠다 라는 좀 이런 태세의 전환도 필요하고 정부도 적극적으로 나서야 합니다.",
            ],
            expected_completed=[],
            expected_pending="",
            expected_final=[
                "이거를 우리가 끌고 가겠다 라는 좀 이런 태세의 전환도 필요하고 정부도 적극적으로 나서야 합니다.",
                "라는 좀 이런 태세의 전환도.",
            ],
            expected_staged="",
            tags=("case-definition-review",),
            sentence_finalize_age=3,
        )
        results = [
            {
                "id": case.id,
                "language": case.language,
                "tags": list(case.tags),
                "expected_final": case.expected_final,
                "chunks": [{"input": chunk} for chunk in case.chunks],
                "actual_final": [
                    "이거를 우리가 끌고 가겠다 라는 좀 이런 태세의 전환도 필요하고 정부도 적극적으로 나서야 합니다."
                ],
                "actual_pending": "",
                "actual_staged": "",
                "actual_staged_queue": [],
                "final_score": _score(1.0, 0.5, 0.6666666667),
                "final_ordered_score": _score(1.0, 0.5, 0.6666666667),
                "final_boundary_score": _score(1.0, 0.5, 0.6666666667),
                "completed_last_score": _score(1.0, 0.5, 0.6666666667),
                "pending_exact": True,
                "staged_exact": True,
                "case_exact_match": False,
                "metrics": {"finalized": 1, "stage_start": 1},
            }
        ]

        report = build_benchmark_report(
            args=args,
            case_sources=["cases.jsonl"],
            corpus_role="challenge-replay",
            cases=[case],
            results=results,
            metric_totals={"finalized": 1, "stage_start": 1},
            elapsed_ms=1.0,
        )

        self.assertEqual(
            report["cases"][0]["case_definition_flags"],
            ["short_contained_expected_token_sentence"],
        )
        self.assertEqual(
            report["case_definition_action_summary"]["action_counts"],
            {"rewrite_expected_final_to_final_sentence_boundary": 1},
        )
        self.assertEqual(report["strict_logic_candidate_summary"]["strict_case_count"], 0)

    def test_short_expected_supported_by_longer_sentence_is_case_definition_review(self) -> None:
        args = Namespace(
            model="sat-3l-sm",
            device="cuda",
            compute_type="float16",
            min_final_f1=0.0,
            fail_on_regression=False,
        )
        case = SbdCase(
            id="short-supported-by-longer-expected",
            language="ko",
            chunks=[
                "이거를 우리가 끌고 가겠다 라는 좀 이런 태세의 전환도 필요하고 정부도.",
                "끌고 가겠다 라는 좀 이런 태세의 전환도 필요하고 정부도.",
                "라는 좀 이런 태세의 전환.",
            ],
            expected_completed=[],
            expected_pending="",
            expected_final=[
                "이거를 우리가 끌고 가겠다 라는 좀 이런 태세의 전환도 필요하고 정부도.",
                "라는 좀 이런 태세의 전환.",
            ],
            expected_staged="",
            tags=("case-definition-review",),
            sentence_finalize_age=3,
        )
        results = [
            {
                "id": case.id,
                "language": case.language,
                "tags": list(case.tags),
                "expected_final": case.expected_final,
                "chunks": [{"input": chunk} for chunk in case.chunks],
                "actual_final": ["이거를 우리가 끌고 가겠다 라는 좀 이런 태세의 전환도 필요하고 정부도."],
                "actual_pending": "라는 좀 이런 태세의 전환.",
                "actual_staged": "",
                "actual_staged_queue": [],
                "final_score": _score(1.0, 0.5, 0.6666666667),
                "final_ordered_score": _score(1.0, 0.5, 0.6666666667),
                "final_boundary_score": _score(1.0, 0.5, 0.6666666667),
                "completed_last_score": _score(1.0, 0.5, 0.6666666667),
                "pending_exact": True,
                "staged_exact": True,
                "case_exact_match": False,
                "metrics": {"finalized": 1, "stage_start": 1},
            }
        ]

        report = build_benchmark_report(
            args=args,
            case_sources=["cases.jsonl"],
            corpus_role="challenge-replay",
            cases=[case],
            results=results,
            metric_totals={"finalized": 1, "stage_start": 1},
            elapsed_ms=1.0,
        )

        self.assertEqual(
            report["cases"][0]["case_definition_flags"],
            ["short_expected_supported_by_longer_sentence"],
        )
        self.assertEqual(
            report["case_definition_action_summary"]["action_counts"],
            {"rewrite_expected_final_to_final_sentence_boundary": 1},
        )
        self.assertEqual(report["strict_logic_candidate_summary"]["strict_case_count"], 0)

    def test_app_quality_blocked_expected_sentence_is_case_definition_review(self) -> None:
        args = Namespace(
            model="sat-3l-sm",
            device="cuda",
            compute_type="float16",
            min_final_f1=0.0,
            fail_on_regression=False,
        )
        case = SbdCase(
            id="app-quality-blocked-expected",
            language="zh",
            chunks=["哈哈哈哈。好浓的猪手。", "哈哈哈哈。好浓的猪手。", "哈哈哈哈。好浓的猪手。"],
            expected_completed=[],
            expected_pending="",
            expected_final=["哈哈哈哈。", "好浓的猪手。"],
            expected_staged="",
            tags=("case-definition-review",),
            sentence_finalize_age=3,
        )
        results = [
            {
                "id": case.id,
                "language": case.language,
                "tags": list(case.tags),
                "expected_final": case.expected_final,
                "chunks": [{"input": chunk} for chunk in case.chunks],
                "actual_final": ["好浓的猪手。"],
                "actual_pending": "",
                "actual_staged": "",
                "actual_staged_queue": [],
                "final_score": _score(1.0, 0.5, 0.6666666667),
                "final_ordered_score": _score(1.0, 0.5, 0.6666666667),
                "final_boundary_score": _score(1.0, 0.5, 0.6666666667),
                "completed_last_score": _score(1.0, 0.5, 0.6666666667),
                "pending_exact": True,
                "staged_exact": True,
                "case_exact_match": False,
                "metrics": {"finalized": 1, "stage_start": 1, "stage_candidate_quality_blocked": 1},
            }
        ]

        report = build_benchmark_report(
            args=args,
            case_sources=["cases.jsonl"],
            corpus_role="challenge-replay",
            cases=[case],
            results=results,
            metric_totals={"finalized": 1, "stage_start": 1, "stage_candidate_quality_blocked": 1},
            elapsed_ms=1.0,
        )

        self.assertEqual(
            report["cases"][0]["case_definition_flags"],
            ["expected_app_quality_blocked_sentence"],
        )
        self.assertEqual(
            report["case_definition_action_summary"]["action_counts"],
            {"rewrite_expected_final_to_final_sentence_boundary": 1},
        )
        self.assertEqual(report["strict_logic_candidate_summary"]["strict_case_count"], 0)

    def test_punctuation_only_final_mismatch_is_boundary_review(self) -> None:
        args = Namespace(
            model="sat-3l-sm",
            device="cuda",
            compute_type="float16",
            min_final_f1=0.0,
            fail_on_regression=False,
        )
        case = SbdCase(
            id="punctuation-only-final-mismatch",
            language="ko",
            chunks=[
                "만약에 그렇게 될 경우에는 가장 큰 피해를 보는 나라는 뭐 OO같은 나라가 되겠죠",
                "그렇게 될 경우에는 가장 큰 피해를 보는 나라는 뭐 OO같은 나라가 되겠죠.",
                "피해를 보는 나라는 뭐 OO같은 나라가 되겠죠",
            ],
            expected_completed=[],
            expected_pending="",
            expected_final=["만약에 그렇게 될 경우에는 가장 큰 피해를 보는 나라는 뭐 OO같은 나라가 되겠죠."],
            expected_staged="",
            tags=("missing-final",),
            sentence_finalize_age=3,
        )
        results = [
            {
                "id": "punctuation-only-final-mismatch",
                "language": "ko",
                "tags": ["missing-final"],
                "expected_final": ["만약에 그렇게 될 경우에는 가장 큰 피해를 보는 나라는 뭐 OO같은 나라가 되겠죠."],
                "chunks": [{"input": chunk} for chunk in case.chunks],
                "actual_final": ["만약에 그렇게 될 경우에는 가장 큰 피해를 보는 나라는 뭐 OO같은 나라가 되겠죠"],
                "actual_pending": "",
                "actual_staged": "",
                "actual_staged_queue": [],
                "final_score": _score(1.0, 1.0, 1.0),
                "final_ordered_score": _score(1.0, 1.0, 1.0),
                "final_boundary_score": _score(0.0, 0.0, 0.0),
                "completed_last_score": _score(1.0, 1.0, 1.0),
                "pending_exact": True,
                "staged_exact": True,
                "case_exact_match": False,
                "metrics": {"finalized": 1, "stage_start": 1},
            }
        ]

        report = build_benchmark_report(
            args=args,
            case_sources=["cases.jsonl"],
            corpus_role="challenge-replay",
            cases=[case],
            results=results,
            metric_totals={"finalized": 1, "stage_start": 1},
            elapsed_ms=1.0,
        )

        self.assertEqual(report["cases"][0]["case_definition_flags"], ["punctuation_only_final_mismatch"])
        self.assertEqual(report["case_definition_action_summary"]["action_counts"], {"manual_boundary_review": 1})
        self.assertEqual(report["strict_logic_candidate_summary"]["strict_case_count"], 0)

    def test_expected_final_matching_combined_staged_queue_is_replay_tail_review(self) -> None:
        args = Namespace(
            model="sat-3l-sm",
            device="cuda",
            compute_type="float16",
            min_final_f1=0.0,
            fail_on_regression=False,
        )
        case = SbdCase(
            id="combined-staged-queue-residue",
            language="zh",
            chunks=[
                "时间真的是过得真快，去年呢，李酷生日呢，我们也是。",
                "时间真的是过得真快。去年呢，李酷生日呢，我们也是到那个汉江。",
                "帽子。时间真的是过得真快。去年呢，李酷生日呢，我们也是到那个汉江公园那里去演。",
            ],
            expected_completed=[],
            expected_pending="",
            expected_final=["时间真的是过得真快，去年呢，李酷生日呢，我们也是。"],
            expected_staged="",
            tags=("missing-final",),
            sentence_finalize_age=3,
        )
        results = [
            {
                "id": "combined-staged-queue-residue",
                "language": "zh",
                "tags": ["missing-final"],
                "expected_final": ["时间真的是过得真快，去年呢，李酷生日呢，我们也是。"],
                "chunks": [{"input": chunk} for chunk in case.chunks],
                "actual_final": [],
                "actual_pending": "",
                "actual_staged": "时间真的是过得真快。",
                "actual_staged_queue": ["去年呢，李酷生日呢，我们也是到那个汉江公园那里去演。"],
                "final_score": _score(0.0, 0.0, 0.0),
                "final_ordered_score": _score(0.0, 0.0, 0.0),
                "final_boundary_score": _score(0.0, 0.0, 0.0),
                "completed_last_score": _score(0.0, 0.0, 0.0),
                "pending_exact": True,
                "staged_exact": False,
                "case_exact_match": False,
                "metrics": {"stage_start": 1, "stage_queue_enqueue": 1},
            }
        ]

        report = build_benchmark_report(
            args=args,
            case_sources=["cases.jsonl"],
            corpus_role="challenge-replay",
            cases=[case],
            results=results,
            metric_totals={"stage_start": 1, "stage_queue_enqueue": 1},
            elapsed_ms=1.0,
        )

        self.assertEqual(report["cases"][0]["case_definition_flags"], [])
        self.assertEqual(
            report["case_definition_action_summary"]["action_counts"],
            {"extend_replay_tail_or_reclassify_staged_expectation": 1},
        )
        self.assertEqual(report["strict_logic_candidate_summary"]["strict_case_count"], 0)

    def test_stable_repeated_expected_final_staged_residue_is_replay_tail_review(self) -> None:
        args = Namespace(
            model="sat-3l-sm",
            device="cuda",
            compute_type="float16",
            min_final_f1=0.0,
            fail_on_regression=False,
        )
        case = SbdCase(
            id="stable-staged-residue",
            language="zh",
            chunks=[
                "时间真的是过得真快。",
                "帽子。时间真的是过得真快。",
                "帽子。时间真的是过得真快。去年呢，李酷生日呢。",
            ],
            expected_completed=[],
            expected_pending="",
            expected_final=["时间真的是过得真快。"],
            expected_staged="",
            tags=("missing-final",),
            sentence_finalize_age=3,
        )
        results = [
            {
                "id": "stable-staged-residue",
                "language": "zh",
                "tags": ["missing-final"],
                "expected_final": ["时间真的是过得真快。"],
                "chunks": [{"input": chunk} for chunk in case.chunks],
                "actual_final": [],
                "actual_pending": "",
                "actual_staged": "时间真的是过得真快。",
                "actual_staged_queue": [],
                "final_score": _score(0.0, 0.0, 0.0),
                "final_ordered_score": _score(0.0, 0.0, 0.0),
                "final_boundary_score": _score(0.0, 0.0, 0.0),
                "completed_last_score": _score(0.0, 0.0, 0.0),
                "pending_exact": True,
                "staged_exact": False,
                "case_exact_match": False,
                "metrics": {"stage_start": 1, "stage_age_hold": 1},
            }
        ]

        report = build_benchmark_report(
            args=args,
            case_sources=["cases.jsonl"],
            corpus_role="challenge-replay",
            cases=[case],
            results=results,
            metric_totals={"stage_start": 1, "stage_age_hold": 1},
            elapsed_ms=1.0,
        )

        self.assertEqual(
            report["case_definition_action_summary"]["action_counts"],
            {"extend_replay_tail_or_reclassify_staged_expectation": 1},
        )
        self.assertEqual(report["case_definition_health_summary"]["case_definition_review_count"], 1)
        self.assertEqual(report["case_definition_health_summary"]["case_definition_cleanup_count"], 0)
        self.assertEqual(report["case_definition_health_summary"]["case_interpretation_review_count"], 1)
        self.assertEqual(report["strict_logic_candidate_summary"]["strict_case_count"], 0)

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
            {"rewrite_expected_final_to_final_sentence_boundary": 1},
        )
        self.assertIn("lowercase_or_connector_start", action_summary["expected_quality_flag_counts"])
        self.assertEqual(
            action_summary["by_action"]["rewrite_expected_final_to_final_sentence_boundary"]["examples"][0]["id"],
            "fragment-expected",
        )
        self.assertEqual(report["strict_logic_candidate_summary"]["strict_case_count"], 0)

    def test_human_corrected_expected_final_is_observed_stt_text_review_action(self) -> None:
        args = Namespace(
            model="sat-3l-sm",
            device="cuda",
            compute_type="float16",
            min_final_f1=0.0,
            fail_on_regression=False,
        )
        case = SbdCase(
            id="human-corrected-stt",
            language="zh",
            chunks=["提灯灯面，这个可以点。"],
            expected_completed=[],
            expected_pending="",
            expected_final=["十八梯灯灯面，这个可以点。"],
            expected_staged="",
            tags=("missing-final",),
            sentence_finalize_age=3,
        )
        results = [
            {
                "id": "human-corrected-stt",
                "language": "zh",
                "tags": ["missing-final"],
                "expected_final": ["十八梯灯灯面，这个可以点。"],
                "chunks": [{"input": "提灯灯面，这个可以点。"}],
                "initial_final": [],
                "actual_final": ["提灯灯面，这个可以点。"],
                "actual_pending": "",
                "actual_staged": "",
                "actual_staged_queue": [],
                "final_score": _score(0.8, 0.8, 0.8),
                "final_ordered_score": _score(0.8, 0.8, 0.8),
                "final_boundary_score": _score(1.0, 1.0, 1.0),
                "completed_last_score": _score(0.0, 0.0, 0.0),
                "pending_exact": True,
                "staged_exact": True,
                "case_exact_match": False,
                "metrics": {"finalized": 1, "stage_start": 1},
            }
        ]

        report = build_benchmark_report(
            args=args,
            case_sources=["cases.jsonl"],
            corpus_role="challenge-replay",
            cases=[case],
            results=results,
            metric_totals={"finalized": 1, "stage_start": 1},
            elapsed_ms=1.0,
        )

        action_summary = report["case_definition_action_summary"]
        self.assertEqual(
            action_summary["action_counts"],
            {"rewrite_expected_final_to_observed_stt_text": 1},
        )
        self.assertEqual(report["cases"][0]["input_evidence"]["covered_count"], 1)
        self.assertEqual(report["cases"][0]["input_evidence"]["observed_count"], 0)
        self.assertFalse(report["cases"][0]["input_evidence"]["observed_fully_supported"])
        self.assertEqual(report["strict_logic_candidate_summary"]["strict_case_count"], 0)

    def test_stable_repeat_mismatch_action_reports_candidate_shape(self) -> None:
        args = Namespace(
            model="sat-3l-sm",
            device="cuda",
            compute_type="float16",
            min_final_f1=0.0,
            fail_on_regression=False,
        )
        case = SbdCase(
            id="stable-repeat-shape",
            language="en",
            chunks=[
                "Alpha sentence.",
                "Alpha sentence.",
                "Alpha sentence.",
            ],
            expected_completed=[],
            expected_pending="",
            expected_final=["Alpha sentence.", "Beta sentence."],
            expected_staged="",
            tags=("missing-final",),
            sentence_finalize_age=3,
        )
        results = [
            {
                "id": "stable-repeat-shape",
                "language": "en",
                "tags": ["missing-final"],
                "expected_final": ["Alpha sentence.", "Beta sentence."],
                "chunks": [
                    {"input": "Alpha sentence."},
                    {"input": "Alpha sentence."},
                    {"input": "Alpha sentence."},
                ],
                "initial_final": [],
                "actual_final": ["Alpha sentence."],
                "actual_pending": "",
                "actual_staged": "",
                "actual_staged_queue": [],
                "final_score": _score(1.0, 0.5, 0.667),
                "final_ordered_score": _score(1.0, 0.5, 0.667),
                "final_boundary_score": _score(1.0, 0.5, 0.667),
                "completed_last_score": _score(0.0, 0.0, 0.0),
                "pending_exact": True,
                "staged_exact": True,
                "case_exact_match": False,
                "metrics": {"finalized": 1, "stage_start": 1},
            }
        ]

        report = build_benchmark_report(
            args=args,
            case_sources=["cases.jsonl"],
            corpus_role="challenge-replay",
            cases=[case],
            results=results,
            metric_totals={"finalized": 1, "stage_start": 1},
            elapsed_ms=1.0,
        )

        action_summary = report["case_definition_action_summary"]
        self.assertEqual(
            action_summary["action_counts"],
            {"recut_or_relabel_stable_candidate_mismatch": 1},
        )
        self.assertEqual(
            action_summary["stable_candidate_shape_counts"],
            {"fewer_stable_candidates_than_expected": 1},
        )
        self.assertEqual(
            action_summary["by_action"]["rewrite_expected_final_to_stable_repeated_candidate"][
                "stable_candidate_shape_counts"
            ],
            {},
        )
        self.assertEqual(
            action_summary["by_action"]["recut_or_relabel_stable_candidate_mismatch"][
                "stable_candidate_shape_counts"
            ],
            {"fewer_stable_candidates_than_expected": 1},
        )
        self.assertEqual(
            action_summary["stable_candidate_ordered_alignment_counts"],
            {"candidate_count_mismatch": 1},
        )
        self.assertEqual(
            action_summary["by_action"]["recut_or_relabel_stable_candidate_mismatch"][
                "stable_candidate_ordered_alignment_counts"
            ],
            {"candidate_count_mismatch": 1},
        )
        self.assertEqual(
            action_summary["by_action"]["recut_or_relabel_stable_candidate_mismatch"]["examples"][0][
                "stable_candidate_shape"
            ],
            "fewer_stable_candidates_than_expected",
        )
        self.assertEqual(
            action_summary["by_action"]["recut_or_relabel_stable_candidate_mismatch"]["examples"][0][
                "stable_candidate_ordered_alignment"
            ],
            "candidate_count_mismatch",
        )
        self.assertEqual(
            action_summary["by_action"]["recut_or_relabel_stable_candidate_mismatch"]["examples"][0]["expected_final"],
            ["Alpha sentence.", "Beta sentence."],
        )
        self.assertEqual(
            action_summary["by_action"]["recut_or_relabel_stable_candidate_mismatch"]["examples"][0]["actual_final"],
            ["Alpha sentence."],
        )
        self.assertEqual(
            action_summary["by_action"]["recut_or_relabel_stable_candidate_mismatch"]["examples"][0][
                "stable_candidates"
            ],
            [{"text": "Alpha sentence.", "count": 3, "first_index": 0, "last_index": 2}],
        )
        cleanup_summary = report["case_definition_cleanup_queue_summary"]
        self.assertEqual(cleanup_summary["case_count"], 1)
        self.assertEqual(
            cleanup_summary["queue_counts"],
            {"expected_final_over_specified_or_window_too_short": 1},
        )
        cleanup_item = cleanup_summary["by_queue"]["expected_final_over_specified_or_window_too_short"]
        self.assertEqual(
            cleanup_item["stable_candidate_shape_counts"],
            {"fewer_stable_candidates_than_expected": 1},
        )
        self.assertEqual(
            cleanup_item["stable_candidate_ordered_alignment_counts"],
            {"candidate_count_mismatch": 1},
        )
        self.assertEqual(
            cleanup_item["examples"][0]["stable_candidates"],
            [{"text": "Alpha sentence.", "count": 3, "first_index": 0, "last_index": 2}],
        )
        self.assertEqual(report["cases"][0]["input_evidence"]["stable_candidate_count"], 1)
        self.assertEqual(report["cases"][0]["input_evidence"]["stable_repeat_count"], 1)
        self.assertEqual(report["strict_logic_candidate_summary"]["strict_case_count"], 0)
        self.assertEqual(report["tuning_next_action_summary"]["priority"], "case_definition_cleanup")
        self.assertEqual(report["tuning_next_action_summary"]["case_definition_cleanup_queue_count"], 1)

    def test_terminal_staged_expected_final_is_tail_review_action(self) -> None:
        args = Namespace(
            model="sat-3l-sm",
            device="cuda",
            compute_type="float16",
            min_final_f1=0.0,
            fail_on_regression=False,
        )
        case = SbdCase(
            id="terminal-staged",
            language="en",
            chunks=["First sentence. The target sentence is complete."],
            expected_completed=[],
            expected_pending="",
            expected_final=["First sentence.", "The target sentence is complete."],
            expected_staged="",
            tags=("missing-final",),
            sentence_finalize_age=3,
        )
        results = [
            {
                "id": "terminal-staged",
                "language": "en",
                "tags": ["missing-final"],
                "expected_final": ["First sentence.", "The target sentence is complete."],
                "chunks": [{"input": "First sentence. The target sentence is complete."}],
                "initial_final": [],
                "actual_final": ["First sentence."],
                "actual_pending": "",
                "actual_staged": "The target sentence is complete.",
                "actual_staged_queue": [],
                "final_score": _score(1.0, 0.5, 0.667),
                "final_ordered_score": _score(1.0, 0.5, 0.667),
                "final_boundary_score": _score(1.0, 0.5, 0.667),
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
            {"extend_replay_tail_or_reclassify_staged_expectation": 1},
        )
        self.assertEqual(
            action_summary["by_action"]["extend_replay_tail_or_reclassify_staged_expectation"]["examples"][0][
                "id"
            ],
            "terminal-staged",
        )
        self.assertEqual(
            [item["id"] for item in action_summary["review_cases"]],
            ["terminal-staged"],
        )
        self.assertEqual(report["strict_logic_candidate_summary"]["strict_case_count"], 0)

    def test_terminal_suffix_residue_is_tail_review_action(self) -> None:
        args = Namespace(
            model="sat-3l-sm",
            device="cuda",
            compute_type="float16",
            min_final_f1=0.0,
            fail_on_regression=False,
        )
        cases = [
            SbdCase(
                id="long-suffix",
                language="zh",
                chunks=["我感觉我就是在一层的一个大广场上，结果我往下看，我实际现在在二十二层哎。"],
                expected_completed=[],
                expected_pending="",
                expected_final=["我感觉我就是在一层的一个大广场上，结果我往下看，我实际现在在二十二层哎。"],
                expected_staged="",
                tags=("missing-final",),
                sentence_finalize_age=3,
            ),
            SbdCase(
                id="short-suffix",
                language="zh",
                chunks=["哦，是那里一间。"],
                expected_completed=[],
                expected_pending="",
                expected_final=["哦，是那里一间。"],
                expected_staged="",
                tags=("missing-final",),
                sentence_finalize_age=3,
            ),
        ]
        results = [
            {
                "id": "long-suffix",
                "language": "zh",
                "tags": ["missing-final"],
                "expected_final": ["我感觉我就是在一层的一个大广场上，结果我往下看，我实际现在在二十二层哎。"],
                "chunks": [{"input": "我感觉我就是在一层的一个大广场上，结果我往下看，我实际现在在二十二层哎。"}],
                "initial_final": [],
                "actual_final": ["我感觉我就是在一层的一个大广场上，结果我忘。"],
                "actual_pending": "",
                "actual_staged": "往下看我实际现在在二十二层哎。",
                "actual_staged_queue": [],
                "final_score": _score(0.5, 0.5, 0.5),
                "final_ordered_score": _score(0.5, 0.5, 0.5),
                "final_boundary_score": _score(0.0, 0.0, 0.0),
                "completed_last_score": _score(0.0, 0.0, 0.0),
                "pending_exact": True,
                "staged_exact": False,
                "case_exact_match": False,
                "metrics": {"stage_start": 1},
            },
            {
                "id": "short-suffix",
                "language": "zh",
                "tags": ["missing-final"],
                "expected_final": ["哦，是那里一间。"],
                "chunks": [{"input": "哦，是那里一间。"}],
                "initial_final": [],
                "actual_final": ["哦，是那里。"],
                "actual_pending": "",
                "actual_staged": "一件。",
                "actual_staged_queue": [],
                "final_score": _score(0.5, 0.5, 0.5),
                "final_ordered_score": _score(0.5, 0.5, 0.5),
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
            metric_totals={"stage_start": 2},
            elapsed_ms=1.0,
        )

        action_summary = report["case_definition_action_summary"]
        self.assertEqual(
            action_summary["action_counts"],
            {"extend_replay_tail_or_reclassify_staged_expectation": 1},
        )
        self.assertEqual(
            action_summary["by_action"]["extend_replay_tail_or_reclassify_staged_expectation"]["examples"][0][
                "id"
            ],
            "long-suffix",
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
                "id": "active-pending",
                "language": "ko",
                "tags": ["missing-final"],
                "expected_final": ["expected"],
                "actual_final": ["actual"],
                "actual_staged_queue": ["queued one", "queued two"],
                "actual_staged": "active",
                "actual_pending": "pending",
                "final_score": _score(0.2, 0.2, 0.2),
                "final_boundary_score": _score(0.0, 0.0, 0.0),
                "metrics": {"stage_age_quality_blocked": 2, "stage_revision": 3},
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
        self.assertEqual(summary["top_active_or_pending_residue_cases"][0]["id"], "active-pending")
        self.assertEqual(summary["top_active_or_pending_residue_cases"][0]["actual_staged_preview"], "active")
        self.assertEqual(summary["top_active_or_pending_residue_cases"][0]["actual_pending_preview"], "pending")
        self.assertEqual(summary["top_active_or_pending_residue_cases"][0]["stage_age_quality_blocked"], 2)

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
