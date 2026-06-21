import tempfile
import unittest
from pathlib import Path

from tests.eval.dictation_ai.paper.audit_paper_reference_scope import (
    audit_paper_reference_scope,
)


class DictationAiPaperReferenceScopeAuditTest(unittest.TestCase):
    def test_audit_passes_when_comparison_reference_has_guard_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            paper = Path(tmpdir) / "paper.md"
            paper.write_text(
                "Rao et al. https://isl.iar.kit.edu/downloads/803_Interspeech-2007_Rao.pdf "
                "자료는 비교 근거이며 현재 구현의 직접 근거로 사용하지 않는다.",
                encoding="utf-8",
            )

            result = audit_paper_reference_scope(paper)

        self.assertTrue(result["ok"])
        self.assertEqual(result["missing_comparison_guards"], [])
        self.assertEqual(result["excluded_references"], [])

    def test_audit_reports_comparison_reference_without_guard_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            paper = Path(tmpdir) / "paper.md"
            paper.write_text(
                "Rao et al. https://isl.iar.kit.edu/downloads/803_Interspeech-2007_Rao.pdf",
                encoding="utf-8",
            )

            result = audit_paper_reference_scope(paper)

        self.assertFalse(result["ok"])
        self.assertEqual(
            [item["url"] for item in result["missing_comparison_guards"]],
            ["https://isl.iar.kit.edu/downloads/803_Interspeech-2007_Rao.pdf"],
        )

    def test_audit_reports_excluded_reference_urls(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            paper = Path(tmpdir) / "paper.md"
            paper.write_text(
                "제외 문헌 https://aclanthology.org/2002.iwslt-1.15.pdf",
                encoding="utf-8",
            )

            result = audit_paper_reference_scope(paper)

        self.assertFalse(result["ok"])
        self.assertEqual(
            [item["url"] for item in result["excluded_references"]],
            ["https://aclanthology.org/2002.iwslt-1.15.pdf"],
        )


if __name__ == "__main__":
    unittest.main()
