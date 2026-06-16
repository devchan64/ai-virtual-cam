import unittest

from src.app.sentence_boundary import LegacyRegexSentenceBoundaryDetector
from src.app.dictation_window import _collapse_adjacent_repeated_phrase_details, _collapse_adjacent_repeated_phrases, _diagnostic_tail, _forced_sentence_reason, _new_text_delta, _pending_new_text_combined, _sentence_max_age_chunks, _sentence_output_delta, _sentence_required_confirmations, _sentences_are_revisions, _should_age_staged_sentence, _prefer_sentence_revision, _sentence_end_count, _split_completed_sentences, _stable_window_text


class WhisperRepeatCollapseTest(unittest.TestCase):
    def test_collapse_adjacent_repeated_phrases(self) -> None:
        self.assertEqual(
            _collapse_adjacent_repeated_phrases(
                "job there we'll find out how job there we'll find out how FSD handles"
            ),
            "job there we'll find out how FSD handles",
        )

    def test_collapse_adjacent_repeated_phrases_keeps_non_adjacent_repetition(self) -> None:
        self.assertEqual(
            _collapse_adjacent_repeated_phrases("very nice no braking for the bird very good"),
            "very nice no braking for the bird very good",
        )

    def test_collapse_repeated_like_lets_say_phrase_from_log(self) -> None:
        self.assertEqual(
            _collapse_adjacent_repeated_phrases(
                "like let's say i just want to go right here I'll hold it on the map like let's say i just want to go right here i'll hold it"
            ),
            "like let's say i just want to go right here I'll hold it on the map",
        )

    def test_collapse_repeated_tap_close_phrase_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 100-102.
        text = "Just tap on that lightning bolt icon and it will automatically open your charge port and you can tap on it again to close You can tap on it again to close it."

        self.assertEqual(
            _collapse_adjacent_repeated_phrases(text),
            "Just tap on that lightning bolt icon and it will automatically open your charge port and you can tap on it again to close it.",
        )

    def test_collapse_repeated_prefix_before_hyphenated_phrase_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 592-594.
        text = "EPA estimated ranges are a best best-case scenario, so it's not really the daily reality."

        self.assertEqual(
            _collapse_adjacent_repeated_phrases(text),
            "EPA estimated ranges are a best-case scenario, so it's not really the daily reality.",
        )

    def test_collapse_repeated_phrase_with_variant_leading_word_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 132-143.
        text = "Right now, Fantech is running some fantic is running some huge discounts where you can get 45% off the X8 Apex"

        self.assertEqual(
            _collapse_adjacent_repeated_phrases(text),
            "Right now, Fantech is running some huge discounts where you can get 45% off the X8 Apex",
        )

    def test_collapse_numeric_value_revision_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 29-30.
        text = "Tesla's cars is the fact that these are over one thousand dollars worth These are over $1,000 worth of Tesla accessories."

        self.assertEqual(
            _collapse_adjacent_repeated_phrases(text),
            "Tesla's cars is the fact that these are over $1,000 worth of Tesla accessories.",
        )

    def test_collapse_adjacent_duplicate_determiner_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 35-36.
        text = "Half of them are from tesla and the The Tesla Model"

        self.assertEqual(
            _collapse_adjacent_repeated_phrases(text),
            "Half of them are from tesla and The Tesla Model",
        )

    def test_collapse_korean_compact_question_revision_from_log(self) -> None:
        text = "그래서 첫 번째 질문이 첫번째 질문이 그거예요"

        self.assertEqual(
            _collapse_adjacent_repeated_phrases(text),
            "그래서 첫번째 질문이 그거예요",
        )

    def test_collapse_korean_compact_name_spacing_revision_from_log(self) -> None:
        text = "이제 케빈워시가 들어왔으니까 케빈워시는 케빈 워시가 들어왔으니까 케빈 워시는 결국에는"

        self.assertEqual(
            _collapse_adjacent_repeated_phrases(text),
            "이제 케빈 워시가 들어왔으니까 케빈 워시는 결국에는",
        )

    def test_collapse_korean_long_compact_revision_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 20-34 on 2026-06-13.
        text = "이제 케빈 오씨가 들어왔으니까 케빈 이제 케빈워시가 들어왔으니까 케빈워시는 케빈 워시가 들어왔으니까 케빈 워시는 결국에는 들어왔으니까 케빈워시는 결국에는 트럼프의 사람이니까 결국에는 금리를 화끈하게 내려주지 않겠어라는 않겠어? 라는 질문이신거죠?"

        collapsed, rules = _collapse_adjacent_repeated_phrase_details(text)

        self.assertEqual(
            collapsed,
            "이제 케빈 오씨가 들어왔으니까 케빈 이제 케빈 워시가 들어왔으니까 케빈워시는 결국에는 트럼프의 사람이니까 결국에는 금리를 화끈하게 내려주지 않겠어? 라는 질문이신거죠?",
        )
        self.assertEqual(rules, ["compact_korean", "compact_korean", "compact_korean"])

    def test_collapse_details_report_applied_rules(self) -> None:
        text = "EPA estimated ranges are a best best-case scenario."

        collapsed, rules = _collapse_adjacent_repeated_phrase_details(text)

        self.assertEqual(collapsed, "EPA estimated ranges are a best-case scenario.")
        self.assertEqual(rules, ["hyphen_prefix"])

    def test_collapse_repeated_charger_status_phrase_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 319-321.
        text = "location is, how many stalls there are, what the nearby amenities are, and if there's any broken stalls there are what the nearby amenities are and if there's any broken stalls at the current moment if there is a wait time at a particular charger, it will let you know, but a lot of times it will automatically reroute you as well, so you won't have to think about it"

        self.assertEqual(
            _collapse_adjacent_repeated_phrases(text),
            "location is, how many stalls there are, what the nearby amenities are, and if there's any broken stalls at the current moment if there is a wait time at a particular charger, it will let you know, but a lot of times it will automatically reroute you as well, so you won't have to think about it",
        )

    def test_collapse_korean_near_compact_situation_revision_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 96-98 on 2026-06-13.
        text = "그러니까 이게 상황에 그니까 이게 상황에 따라서 그렇게 하더라고요."

        collapsed, rules = _collapse_adjacent_repeated_phrase_details(text)

        self.assertEqual(collapsed, "그러니까 이게 상황에 따라서 그렇게 하더라고요.")
        self.assertEqual(rules, ["compact_korean"])

    def test_collapse_korean_stablecoin_birth_revision_from_monitoring(self) -> None:
        # Regression from 2026-06-13 monitoring chunk 1163.
        text = "이 스테이블 코인은 새로운 화폐의 탄생 이라고 탄생이라고 보셔야 돼요."

        collapsed, rules = _collapse_adjacent_repeated_phrase_details(text)

        self.assertEqual(collapsed, "이 스테이블 코인은 새로운 화폐의 탄생이라고 보셔야 돼요.")
        self.assertEqual(rules, ["compact_korean"])

    def test_collapse_korean_last_card_revision_from_monitoring(self) -> None:
        # Regression from 2026-06-13 monitoring chunk 1111.
        text = "그렇다면은 돈은 계속 풀어야 되는데 그렇다면 돈은 계속 풀어야 되는데 마지막 남은"

        collapsed, rules = _collapse_adjacent_repeated_phrase_details(text)

        self.assertEqual(collapsed, "그렇다면은 돈은 계속 풀어야 되는데 마지막 남은")
        self.assertEqual(rules, ["compact_korean"])




    def test_collapse_near_phrase_does_not_remove_chinese_place_name_context_from_log(self) -> None:
        text = "来 的 吉 隆 坡 对 我 们 是 落 地 吉 隆 坡 然 后 玩 了 几 天"
        collapsed, rules = _collapse_adjacent_repeated_phrase_details(text)

        self.assertEqual(collapsed, text)
        self.assertNotIn("near_phrase", rules)

    def test_collapse_adjacent_phrase_still_handles_chinese_exact_duplicate_from_log(self) -> None:
        text = "那 个 汤 底 那 个 汤 底 真 的 有 一 点 辣"
        collapsed, rules = _collapse_adjacent_repeated_phrase_details(text)

        self.assertEqual(collapsed, "那 个 汤 底 真 的 有 一 点 辣")
        self.assertIn("adjacent_phrase", rules)

    def test_collapse_repeated_chinese_clause_from_monitoring(self) -> None:
        text = "这吃五里鸡王。香香香香香香香香。这吃五里鸡王。这吃五里鸡王。"
        collapsed, rules = _collapse_adjacent_repeated_phrase_details(text)

        self.assertEqual(collapsed, "这吃五里鸡王。香香香香香香香香。这吃五里鸡王。")
        self.assertIn("cjk_clause", rules)

    def test_collapse_repeated_short_chinese_clause_run_from_monitoring(self) -> None:
        text = "豆浆，豆浆，豆浆，豆浆。哇，好大一份啊。"
        collapsed, rules = _collapse_adjacent_repeated_phrase_details(text)

        self.assertEqual(collapsed, "豆浆。哇，好大一份啊。")
        self.assertIn("cjk_clause", rules)

if __name__ == "__main__":
    unittest.main()
