import unittest

from src.app.dictation_transcript_logic import (
    _next_revision_confirmation_count,
    _should_reset_revision_age,
)


class DictationAiRevisionResetPolicyTest(unittest.TestCase):
    def test_confirmation_preserves_token_sentence_when_end_mark_flaps(self) -> None:
        previous = "you want to go up there and do something meaningful."
        preferred = "you want to go up there and do something meaningful"

        self.assertFalse(_should_reset_revision_age(previous, preferred))
        self.assertEqual(
            _next_revision_confirmation_count(previous, preferred, 2),
            3,
        )


if __name__ == "__main__":
    unittest.main()
