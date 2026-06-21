import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.eval.dictation_ai.paper.audit_paper_readiness import audit_paper_readiness


class DictationAiPaperReadinessAuditTest(unittest.TestCase):
    def _write_summary(self, path: Path) -> None:
        path.write_text(
            json.dumps(
                {
                    "report_count": 1,
                    "unique_axis_count": 1,
                    "case_set_summary": {
                        "case_count": {"consistent": True, "value": 3, "unique_values": [3]},
                        "expected_final_case_count": {
                            "consistent": True,
                            "value": 3,
                            "unique_values": [3],
                        },
                        "language_counts": {
                            "en": {"consistent": True, "value": 1, "unique_values": [1]},
                            "ko": {"consistent": True, "value": 1, "unique_values": [1]},
                            "zh": {"consistent": True, "value": 1, "unique_values": [1]},
                        },
                    },
                    "baseline_metric_summary": {
                        "final_precision_avg": {
                            "consistent": True,
                            "value": 0.602,
                            "unique_values": [0.602],
                        },
                        "final_recall_avg": {
                            "consistent": True,
                            "value": 0.440,
                            "unique_values": [0.440],
                        },
                        "final_f1_avg": {
                            "consistent": True,
                            "value": 0.483,
                            "unique_values": [0.483],
                        },
                        "final_boundary_f1_avg": {
                            "consistent": True,
                            "value": 0.108,
                            "unique_values": [0.108],
                        },
                        "finalized_per_stage_start": {
                            "consistent": True,
                            "value": 0.712,
                            "unique_values": [0.712],
                        },
                    },
                    "paper_claim_matrix": [
                        {"claim_id": "operating_average_quality", "status": "사용 금지"},
                        {"claim_id": "translation_stability", "status": "보류"},
                        {"claim_id": "raw_stt_accuracy", "status": "사용 금지"},
                        {"claim_id": "runtime_loop_equivalence", "status": "사용 금지"},
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def _write_paper(self, path: Path, *, missing_guard: bool = False) -> None:
        raw_guard = "" if missing_guard else "raw STT 정확도 개선은 주장하지 않는다."
        path.write_text(
            "\n".join(
                [
                    "numbers 1 3 0.602 0.440 0.483 0.108 0.712 en=1 ko=1 zh=1",
                    "운영 평균 품질 주장은 여전히 보류한다.",
                    "translation replay 전에는 성능 주장으로 쓰지 않는다.",
                    raw_guard,
                    "end-to-end runtime 검증으로 표현하지 않는다.",
                ]
            ),
            encoding="utf-8",
        )

    def _write_source_audit(self, path: Path, *, translation_linked: bool = False) -> None:
        segment_linkage = {}
        if translation_linked:
            segment_linkage = {
                "finalize_segment_count": 1,
                "transcript_segment_count": 1,
                "translation_diagnostic_segment_count": 1,
                "translation_segment_count": 1,
                "final_transcript_linked_segment_count": 1,
                "final_translation_diagnostic_linked_segment_count": 1,
                "final_translation_linked_segment_count": 1,
            }
        path.write_text(
            json.dumps(
                {
                    "representative_readiness": {
                        "can_seed_representative_candidates": True,
                    },
                    "marker_counts": {
                        "translation": 1,
                        "translation_diagnostic": 1,
                    },
                    "segment_linkage": segment_linkage,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def _write_packet_validation(self, path: Path) -> None:
        path.write_text(
            json.dumps(
                {
                    "packet_count": 1,
                    "ready_packet_count": 1,
                    "source_window_filter_applied_count": 1,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def _write_draft_validation(self, path: Path) -> None:
        path.write_text(
            json.dumps(
                {
                    "case_count": 1,
                    "corpus_role": "representative",
                    "draft_count": 1,
                    "expected_final_case_count": 0,
                    "language_counts": {"ko": 1},
                    "representative_review_packet_validation": {
                        "packet_count": 1,
                        "ready_packet_count": 1,
                        "matched_case_count": 1,
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def _write_structural_validation(self, path: Path) -> None:
        path.write_text(
            json.dumps(
                {
                    "case_count": 2,
                    "corpus_role": "exploratory",
                    "draft_count": 0,
                    "expected_final_case_count": 2,
                    "language_counts": {"en": 1, "zh": 1},
                    "sources": [
                        ".tmp/eval/dictation-ai-sbd/structural-lifecycle-cases.jsonl"
                    ],
                    "tag_counts": {
                        "structural-lifecycle": 2,
                        "stage-queue": 2,
                        "missing-final": 1,
                        "translation-skip": 1,
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def _write_review_packets(self, path: Path) -> None:
        path.write_text(
            json.dumps(
                {
                    "representative_review_packet_version": 1,
                    "source_manifest": {
                        "sampling_unit": "session-window",
                        "sampling_rule": "session-hash-v1:test",
                        "selected_source_count": 1,
                        "selected_source_counts": {"ko": 1},
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
                            "id": "packet-ko-1",
                            "language": "ko",
                            "source_log": ".tmp/logs/avc-whisper.log",
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
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def _write_report(self, path: Path, *, corpus_role: str = "challenge-replay") -> None:
        if corpus_role == "representative":
            experiment_stage = "representative-replay"
            claim_scope_key = "operating-average-finalization"
            case_summary = {
                "corpus_role": "representative",
                "expected_final_case_count": 3,
                "representative_metadata": {
                    "sampling_unit_counts": {"session-window": 3},
                    "sampling_rule_counts": {"session-hash-v1:test": 3},
                    "source_log_count": 1,
                    "review_packet_count": 1,
                    "expected_final_reviewer_counts": {"reviewer-a": 3},
                },
                "representative_review_packet_validation": {
                    "packet_count": 1,
                    "ready_packet_count": 1,
                    "matched_case_count": 3,
                },
            }
            supported_claims = [
                "operating-average finalization estimate for the sampled population"
            ]
            unsupported_claims = ["failure-mode regression coverage"]
            deferred_claims = ["translation-side churn reduction"]
        else:
            experiment_stage = "challenge-replay"
            claim_scope_key = "failure-lifecycle-tradeoff"
            case_summary = {
                "corpus_role": "challenge-replay",
                "expected_final_case_count": 3,
            }
            supported_claims = [
                "revision lifecycle trade-off on observed failure cases"
            ]
            unsupported_claims = ["operating-average quality"]
            deferred_claims = ["translation-side churn reduction"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "corpus_roles": [corpus_role],
                    "case_summary": case_summary,
                    "evidence_protocol": {
                        "paper_evidence": True,
                        "paper_evidence_eligible": True,
                        "corpus_role": corpus_role,
                        "experiment_stage": experiment_stage,
                        "claim_scope_key": claim_scope_key,
                        "supported_claims": supported_claims,
                        "unsupported_claims": unsupported_claims,
                        "deferred_claims": deferred_claims,
                    },
                    "runtime_contract": {
                        "backend": "sat",
                        "device": "cuda",
                        "compute_type": "float16",
                        "model_source": "local-cache-only",
                    },
                    "parameter_axes": ["SENTENCE_CONFIRM_CHUNKS"],
                    "evidence_summary": {
                        "results": [{"label": "baseline"}],
                        "adoption_review_counts": {},
                    },
                    "lifecycle_replay_contract": {
                        "state_machine_parity": "partial",
                        "shared_decision_helpers": [],
                        "missing_runtime_signals": ["translation request/output linkage"],
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def _run_audit(
        self,
        root: Path,
        *,
        missing_guard: bool = False,
        report_corpus_role: str = "challenge-replay",
        write_structural_result: bool = False,
        translation_linked: bool = False,
    ) -> dict[str, object]:
        summary = root / "summary.json"
        paper = root / "paper.md"
        source = root / "source.json"
        packet_validation = root / "packets.validation.json"
        review_packets = root / "packets.json"
        draft_validation = root / "drafts.validation.json"
        structural_validation = root / "structural.validation.json"
        structural_result = root / "structural-result.json"
        cases = root / "cases"
        report = root / "reports" / "summary.json"
        cases.mkdir()
        self._write_summary(summary)
        self._write_paper(paper, missing_guard=missing_guard)
        self._write_source_audit(source, translation_linked=translation_linked)
        self._write_packet_validation(packet_validation)
        self._write_review_packets(review_packets)
        self._write_draft_validation(draft_validation)
        self._write_structural_validation(structural_validation)
        if write_structural_result:
            structural_result.write_text(
                json.dumps({"summary": {"case_count": 2}}, ensure_ascii=False),
                encoding="utf-8",
            )
        self._write_report(report, corpus_role=report_corpus_role)
        with patch("tests.eval.dictation_ai.cases.sbd_case_paths.SBD_REPRESENTATIVE_CASE_DIR", cases):
            return audit_paper_readiness(
                reports=[report],
                summary_path=summary,
                paper_path=paper,
                source_audit_path=source,
                review_packet_validation_path=packet_validation,
                representative_cases=cases,
                review_packets=review_packets,
                representative_draft_validation=draft_validation,
                structural_preflight_validation=structural_validation,
                structural_preflight_result=structural_result,
            )

    def test_readiness_audit_passes_for_challenge_only_paper_with_followup_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._run_audit(Path(tmpdir))

        self.assertTrue(result["ok"])
        self.assertEqual(result["current_claim_scope"], "challenge-replay-only")
        self.assertEqual(result["followup_readiness"]["representative_draft_count"], 1)
        self.assertTrue(result["followup_readiness"]["representative_draft_traceable"])
        self.assertTrue(result["checks"]["evidence_inventory"])
        self.assertTrue(result["checks"]["methodology"])
        self.assertEqual(
            result["followup_readiness"]["representative_status"],
            "blocked_on_human_expected_final",
        )
        self.assertEqual(
            result["methodology_decision"]["primary_interpretation"],
            "failure-enriched challenge replay lifecycle analysis",
        )
        self.assertEqual(
            result["methodology_decision"]["recommended_next_experiment"],
            "human-review representative expected_final labels",
        )
        self.assertEqual(
            result["methodology_decision"]["threshold_sweep_role"],
            "parameter adoption or rejection evidence, not a universal optimization claim",
        )
        available_experiments = result["methodology_decision"]["available_next_experiments"]
        self.assertEqual(
            [item["name"] for item in available_experiments],
            [
                "human-review representative expected_final labels",
                "build translation replay linkage before translation claims",
                "run structural lifecycle preflight on selected exploratory cases",
            ],
        )
        self.assertEqual(available_experiments[2]["role"], "logic-change preflight")
        self.assertFalse(available_experiments[2]["paper_evidence"])
        self.assertEqual(available_experiments[2]["case_count"], 2)
        self.assertEqual(
            available_experiments[2]["case_path"],
            ".tmp/eval/dictation-ai-sbd/structural-lifecycle-cases.jsonl",
        )
        self.assertEqual(available_experiments[2]["expected_result_path"], str(Path(tmpdir) / "structural-result.json"))
        self.assertFalse(available_experiments[2]["result_exists"])
        self.assertEqual(available_experiments[2]["execution_status"], "input-ready-not-run")
        self.assertIn("--device cuda", available_experiments[2]["preflight_command"])
        self.assertIn(str(Path(tmpdir) / "structural-result.json"), available_experiments[2]["preflight_command"])
        self.assertIn("--paper-evidence", available_experiments[2]["full_challenge_replay_command"])
        self.assertIn(
            "tests/eval/dictation_ai/sbd_cases",
            available_experiments[2]["full_challenge_replay_command"],
        )
        self.assertIn("full 1113-case challenge replay", available_experiments[2]["promotion_requirement"])
        self.assertIn(
            "operating_average_quality",
            result["methodology_decision"]["blocked_claims"],
        )
        self.assertTrue(result["methodology_decision"]["ok"])
        self.assertTrue(result["structural_preflight"]["ready"])

    def test_readiness_audit_reports_translation_replay_when_segment_linkage_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._run_audit(Path(tmpdir), translation_linked=True)

        self.assertEqual(
            result["followup_readiness"]["translation_status"],
            "ready_for_translation_replay_case_building",
        )
        self.assertEqual(
            result["methodology_decision"]["translation_next_experiment"],
            "run translation replay",
        )
        self.assertEqual(
            result["methodology_decision"]["translation_role"],
            "translation replay linkage is ready; run translation replay before stability claims",
        )
        self.assertIn(
            "run translation replay before final-only translation stability claims",
            result["methodology_decision"]["method_reconstruction"],
        )
        self.assertEqual(
            result["methodology_decision"]["available_next_experiments"][1]["blocked_by"],
            "",
        )
        self.assertEqual(result["structural_preflight"]["source_count"], 1)
        self.assertFalse(result["structural_preflight"]["result_exists"])
        self.assertEqual(result["structural_preflight"]["execution_status"], "input-ready-not-run")
        self.assertFalse(result["structural_preflight"]["paper_evidence"])
        self.assertEqual(result["structural_preflight"]["case_count"], 2)
        self.assertEqual(
            result["structural_preflight"]["focus_tag_counts"]["stage-queue"],
            2,
        )

    def test_readiness_audit_fails_when_claim_guard_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._run_audit(Path(tmpdir), missing_guard=True)

        self.assertFalse(result["ok"])
        self.assertFalse(result["checks"]["claim_scope"])

    def test_readiness_audit_fails_when_challenge_only_methodology_has_other_report_scope(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._run_audit(Path(tmpdir), report_corpus_role="representative")

        self.assertFalse(result["ok"])
        self.assertTrue(result["checks"]["evidence_inventory"])
        self.assertFalse(result["checks"]["methodology"])
        self.assertFalse(result["methodology_decision"]["challenge_replay_valid"])

    def test_readiness_audit_marks_structural_preflight_result_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._run_audit(Path(tmpdir), write_structural_result=True)

        structural = result["structural_preflight"]
        self.assertTrue(structural["ready"])
        self.assertTrue(structural["result_exists"])
        self.assertEqual(structural["execution_status"], "result-present")
        available_experiments = result["methodology_decision"]["available_next_experiments"]
        self.assertTrue(available_experiments[2]["result_exists"])
        self.assertEqual(available_experiments[2]["execution_status"], "result-present")


if __name__ == "__main__":
    unittest.main()
