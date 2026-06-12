import unittest

from src.app.transcript_revision import consume_committed_prefix, revision_lifecycle_context


class TranscriptRevisionLifecycleTest(unittest.TestCase):
    def test_forced_candidate_consumes_pending_only_after_final_commit(self) -> None:
        pending = "So we have to go somewhere else to go to the bathroom which takes even more time i have had to take it off"

        self.assertEqual(
            consume_committed_prefix(pending, "So we have to go somewhere else to go to the bathroom"),
            "which takes even more time i have had to take it off",
        )
        self.assertEqual(consume_committed_prefix(pending, pending), "")

    def test_forced_candidate_consumes_pending_after_leading_connective(self) -> None:
        self.assertEqual(
            consume_committed_prefix("And let's do it now.", "let's do it now."),
            "",
        )

    def test_forced_candidate_keeps_tail_after_connective(self) -> None:
        self.assertEqual(
            consume_committed_prefix("And let's do it now again", "let's do it now"),
            "and again",
        )

    def test_revision_lifecycle_context_keeps_staged_and_pending_visible(self) -> None:
        context = revision_lifecycle_context(
            "already committed",
            "forced staged candidate",
            "pending revision tail",
        )

        self.assertEqual(context, "already committed forced staged candidate pending revision tail")


if __name__ == "__main__":
    unittest.main()
