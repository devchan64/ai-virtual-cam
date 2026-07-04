import unittest

from src.app.dictation_core.transcript_revision import append_context, consume_committed_prefix, revision_lifecycle_context


class TranscriptRevisionLifecycleTest(unittest.TestCase):
    def test_final_commit_consumes_matching_pending_prefix(self) -> None:
        pending = "So we have to go somewhere else to go to the bathroom which takes even more time i have had to take it off"

        self.assertEqual(
            consume_committed_prefix(pending, "So we have to go somewhere else to go to the bathroom"),
            "which takes even more time i have had to take it off",
        )
        self.assertEqual(consume_committed_prefix(pending, pending), "")

    def test_final_commit_consumes_pending_after_leading_connective(self) -> None:
        self.assertEqual(
            consume_committed_prefix("And let's do it now.", "let's do it now."),
            "",
        )

    def test_final_commit_keeps_pending_tail_after_connective(self) -> None:
        self.assertEqual(
            consume_committed_prefix("And let's do it now again", "let's do it now"),
            "and again",
        )

    def test_revision_lifecycle_context_keeps_staged_and_pending_visible(self) -> None:
        context = revision_lifecycle_context(
            "already committed",
            "staged candidate",
            "pending revision tail",
        )

        self.assertEqual(context, "already committed staged candidate pending revision tail")

    def test_revision_context_keeps_recent_text_when_overflow(self) -> None:
        base = " ".join(["committed"] * 200)
        staged = " ".join(["staged"] * 200)
        pending = " ".join(["pending"] * 200)

        context = revision_lifecycle_context(base, staged, pending)

        self.assertTrue(len(context) <= 4000)
        self.assertIn("pending", context)
        self.assertIn("staged", context)

    def test_append_context_truncates_oldest_prefix(self) -> None:
        self.assertTrue(
            len(append_context(" ".join(["a"] * 100), " ".join(["b"] * 100), max_chars=80)) <= 80
        )

    def test_consume_committed_prefix_with_connective_and_remaining(self) -> None:
        self.assertEqual(
            consume_committed_prefix("And let's do it now", "let's do it"),
            "and now",
        )


if __name__ == "__main__":
    unittest.main()
