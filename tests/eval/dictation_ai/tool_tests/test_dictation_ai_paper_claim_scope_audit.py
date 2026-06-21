import json
import tempfile
import unittest
from pathlib import Path

from tests.eval.dictation_ai.paper.audit_paper_claim_scope import audit_paper_claim_scope


class DictationAiPaperClaimScopeAuditTest(unittest.TestCase):
    def _write_summary(self, path: Path) -> None:
        path.write_text(
            json.dumps(
                {
                    "paper_claim_matrix": [
                        {"claim_id": "operating_average_quality", "status": "사용 금지"},
                        {"claim_id": "translation_stability", "status": "보류"},
                        {"claim_id": "raw_stt_accuracy", "status": "사용 금지"},
                        {"claim_id": "runtime_loop_equivalence", "status": "사용 금지"},
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def test_audit_passes_when_restricted_claims_have_guard_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            summary = root / "summary.json"
            paper = root / "paper.md"
            self._write_summary(summary)
            paper.write_text(
                "\n".join(
                    [
                        "운영 평균 품질 주장은 여전히 보류한다.",
                        "translation replay 전에는 성능 주장으로 쓰지 않는다.",
                        "raw STT 정확도 개선은 주장하지 않는다.",
                        "end-to-end runtime 검증으로 표현하지 않는다.",
                    ]
                ),
                encoding="utf-8",
            )

            result = audit_paper_claim_scope(summary, paper)

        self.assertTrue(result["ok"])
        self.assertEqual(result["missing_guard_claims"], [])
        self.assertEqual(
            {item["claim_id"] for item in result["restricted_claims"]},
            {
                "operating_average_quality",
                "translation_stability",
                "raw_stt_accuracy",
                "runtime_loop_equivalence",
            },
        )

    def test_audit_reports_restricted_claims_without_guard_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            summary = root / "summary.json"
            paper = root / "paper.md"
            self._write_summary(summary)
            paper.write_text("논문 초안", encoding="utf-8")

            result = audit_paper_claim_scope(summary, paper)

        self.assertFalse(result["ok"])
        self.assertEqual(
            {item["claim_id"] for item in result["missing_guard_claims"]},
            {
                "operating_average_quality",
                "translation_stability",
                "raw_stt_accuracy",
                "runtime_loop_equivalence",
            },
        )

    def test_audit_does_not_accept_raw_stt_improvement_claim_as_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            summary = root / "summary.json"
            paper = root / "paper.md"
            self._write_summary(summary)
            paper.write_text(
                "\n".join(
                    [
                        "운영 평균 품질 주장은 여전히 보류한다.",
                        "translation replay 전에는 성능 주장으로 쓰지 않는다.",
                        "raw STT 정확도가 개선되었다.",
                        "end-to-end runtime 검증으로 표현하지 않는다.",
                    ]
                ),
                encoding="utf-8",
            )

            result = audit_paper_claim_scope(summary, paper)

        self.assertFalse(result["ok"])
        self.assertIn(
            "raw_stt_accuracy",
            {item["claim_id"] for item in result["missing_guard_claims"]},
        )


if __name__ == "__main__":
    unittest.main()
