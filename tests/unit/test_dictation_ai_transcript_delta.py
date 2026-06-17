import unittest

from src.app.sentence_boundary import LegacyRegexSentenceBoundaryDetector
from src.app.dictation_window import _diagnostic_tail, _new_text_delta, _sentence_max_age_chunks, _sentence_output_delta, _sentence_required_confirmations, _sentences_are_revisions, _should_age_staged_sentence, _prefer_sentence_revision, _sentence_end_count, _split_completed_sentences, _stable_window_text


class WhisperTranscriptDeltaTest(unittest.TestCase):
    def test_stable_window_keeps_full_text_without_tail_lag(self) -> None:
        self.assertEqual(
            _stable_window_text("Folks I was one of the first people", 1.0, 4.0),
            "Folks I was one of the first people",
        )

    def test_sentence_output_delta_ignores_committed_sentence_with_punctuation_changes(self) -> None:
        committed = "one of my favorite floor mat sets for this purpose is from today's sponsor last fit"
        sentence = "One of my favorite floor mat sets for this purpose is from today's sponsor, Last Fit."

        self.assertEqual(_sentence_output_delta(committed, sentence), "")

    def test_sentence_output_delta_keeps_new_suffix_after_overlap(self) -> None:
        committed = "i've had these mats for a while now and they have done an excellent job of protecting"
        sentence = "I've had these mats for a while now, and they have done an excellent job of protecting the carpet underneath them."

        self.assertEqual(_sentence_output_delta(committed, sentence), "the carpet underneath them")

    def test_sentence_output_delta_keeps_distinct_sentence(self) -> None:
        sentence = "Here they are after not vacuuming for a couple weeks."

        self.assertEqual(_sentence_output_delta("already committed text", sentence), sentence)

    def test_sentence_output_delta_suppresses_revised_floating_hoping_duplicate_from_log(self) -> None:
        committed = "floating and hoping like a spot spot up three point shooter"
        sentence = "not just floating and hoping like a spot-up three-point shooter."

        self.assertEqual(_sentence_output_delta(committed, sentence), "")

    def test_sentence_output_delta_trims_repeated_hunting_prefix_and_suffix_from_log(self) -> None:
        committed = "It's hunting. No, it's it's honey."
        sentence = "It's hunting like a shark Now, it's hunting."

        self.assertEqual(_sentence_output_delta(committed, sentence), "like a shark now")

    def test_sentence_output_delta_suppresses_short_third_pro_tip_revision_from_log(self) -> None:
        committed = "And a third pro tip, if where like that also."
        sentence = "And the third pro tip, if where you want to go has no name or address or you're not sure if you could find it on the map,"

        self.assertEqual(_sentence_output_delta(committed, sentence), "you want to go has no name or address or you re not sure if you could find it on the map")

    def test_sentence_output_delta_suppresses_numeric_fragment_echo_from_log(self) -> None:
        # Regression from avc-whisper.log: "saying dry weight ... are 6,800 pounds." to "are 6,800 pounds."
        committed = "saying dry weight is around 5,800 pounds and it has a GBWR of 6,800"
        sentence = "are 6,800 pounds."

        self.assertEqual(_sentence_output_delta(committed, sentence), "")

    def test_sentence_output_delta_trims_short_actually_driving_prefix_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 629 and 632.
        committed = "actually driving"
        sentence = "about actually driving before we get into that you may notice an alert right here tesla will send you alerts for like low tire pressure and some other random things if you tap on it it'll tell you what it's for mine says this right here which basically means it doesn't like my phone camera being"

        self.assertEqual(
            _sentence_output_delta(committed, sentence),
            "before we get into that you may notice an alert right here tesla will send you alerts for like low tire pressure and some other random things if you tap on it it ll tell you what it s for mine says this right here which basically means it doesn t like my phone camera being",
        )

    def test_sentence_output_delta_trims_leading_partial_word_overlap_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 180-191.
        committed = "This is very helpful for your road trips there's no need to plug into a supercharger and charge to 100% just to get to the next one there"
        sentence = "charger and charge to 100 just to get to the next one there are plenty of superchargers in the US at least and around most places in the world where you don't need all that battery to continue your trip."

        self.assertEqual(
            _sentence_output_delta(committed, sentence),
            "are plenty of superchargers in the us at least and around most places in the world where you don t need all that battery to continue your trip",
        )

    def test_sentence_output_delta_trims_committed_customization_prefix_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 210-213.
        committed = "But if you want to play with the customization and the menus and all that you can play with it on your own"
        sentence = "customization and the menus and all that you can play with it on your own at the top is your car's name you can customize it in the Tesla menu."

        self.assertEqual(
            _sentence_output_delta(committed, sentence),
            "at the top is your car s name you can customize it in the tesla menu",
        )

    def test_sentence_output_delta_trims_short_again_awesome_prefix_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 283-295.
        committed = "Again awesome."
        sentence = "again awesome the location tab shows your car's live location at any time which is awesome."

        self.assertEqual(
            _sentence_output_delta(committed, sentence),
            "the location tab shows your car s live location at any time which is awesome",
        )

    def test_sentence_output_delta_trims_long_coffee_overlap_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 42-52.
        committed = "once you get used to it it's actually very freeing and it is a wonderful experience especially for me in the morning to have a cup of coffee and just sit here"
        sentence = "cup of coffee and just sit here and enjoy my cup of coffee while I'm an observer of this thing driving"

        self.assertEqual(
            _sentence_output_delta(committed, sentence),
            "and enjoy my cup of coffee while i m an observer of this thing driving",
        )

    def test_sentence_output_delta_trims_fast_boundary_turn_signal_overlap_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 246-256.
        committed = "halfway and another great new feature that came with a recent software update is the automatic turn signal"
        sentence = "turn signal if you when you enable that it'll automatically turn your turn signal off and normally with that before that setting came, when you half-press a turn signal it would go on three blinks and then if you fully press the turn signal it stays"

        self.assertEqual(
            _sentence_output_delta(committed, sentence),
            "when you enable that it ll automatically turn your turn signal off and normally with that before that setting came when you half press a turn signal it would go on three blinks and then if you fully press the turn signal it stays",
        )

    def test_sentence_output_delta_trims_self_driving_tail_reuse_from_log(self) -> None:
        # Regression from avc-whisper.log chunks 34-39.
        committed = "It's also less fatiguing to drive when you're taking more breaks, and then you have the systems like autopilot and full self-driving in tesla vehicles specifically that help to make your drive that much less fatiguing as well"
        sentence = "self-driving and Tesla vehicles specifically that help to make your drive that much less fatiguing as well and make the trade-off worth it for those couple extra minutes spent at chargers."

        self.assertEqual(
            _sentence_output_delta(committed, sentence),
            "and make the trade off worth it for those couple extra minutes spent at chargers",
        )

    def test_delta_outputs_only_new_overlap_suffix(self) -> None:
        committed = "Folks I was one of the first people"
        stable = "the first people in the United States to take delivery"

        self.assertEqual(_new_text_delta(committed, stable), "in the United States to take delivery")

    def test_delta_ignores_already_committed_text(self) -> None:
        committed = "다음 영상에서 만나요"

        self.assertEqual(_new_text_delta(committed, "다음 영상에서 만나요"), "")

    def test_delta_handles_text_without_spaces(self) -> None:
        committed = "你好世界"
        stable = "世界今天很好"

        self.assertEqual(_new_text_delta(committed, stable), "今天很好")

    def test_delta_suppresses_stable_text_already_covered_by_history(self) -> None:
        committed = "Now it is telling me. 52 second. Oh my goodness. Is it true?"
        stable = "52 second. Oh my goodness. Is it true?"

        self.assertEqual(_new_text_delta(committed, stable), "")

    def test_sentence_output_delta_suppresses_suffix_duplicate_from_unplug_log(self) -> None:
        # Regression from avc-whisper.log chunks 438-440.
        self.assertEqual(_sentence_output_delta("Let's do it now.", "do it now."), "")

    def test_sentence_output_delta_suppresses_hi_after_high_from_cost_log(self) -> None:
        # Regression from avc-whisper.log chunks 491-497.
        committed = "And we're in California, so it would be high."

        self.assertEqual(_sentence_output_delta(committed, "Hi."), "")
        self.assertEqual(_sentence_output_delta(committed, "$16.24"), "$16.24")

    def test_sentence_output_delta_suppresses_korean_exact_repeat(self) -> None:
        # Regression from ongoing Korean stream where the same sentence is emitted repeatedly.
        self.assertEqual(_sentence_output_delta("다음 영상에서 만나요.", "다음 영상에서 만나요."), "")
        self.assertEqual(_sentence_output_delta("다음 영상에서 만나요", "다음 영상에서 만나요."), "")

    def test_sentence_output_delta_keeps_on_ramp_tail_from_bathroom_log(self) -> None:
        # Regression from avc-whisper.log chunks 641-653.
        committed = "I have had to take it off of self-driving twice because it continues to have a problem finding the correct on-ramp"
        sentence = "of self driving twice because it continues to have a problem finding the correct on ramp for a freeway"

        self.assertTrue(_sentences_are_revisions(committed, sentence))
        self.assertEqual(_sentence_output_delta(committed, sentence), "for a freeway")

    def test_sentence_output_delta_keeps_short_korean_revision_suffix_from_log(self) -> None:
        self.assertEqual(_sentence_output_delta("재정적 프리미엄이", "재정적 프리미엄이 과거"), "과거")
        self.assertEqual(_sentence_output_delta("바꾸는 모습들로", "바꾸는 모습들로 가져왔잖아요."), "가져왔잖아요")

    def test_sentence_output_delta_suppresses_short_korean_suffix_revision_from_log(self) -> None:
        self.assertTrue(_sentences_are_revisions("투자를 하겠다.", "경우는 투자를 하겠다."))
        self.assertEqual(_sentence_output_delta("투자를 하겠다.", "경우는 투자를 하겠다."), "")

    def test_sentence_output_delta_suppresses_korean_correction_only_revision_from_log(self) -> None:
        committed = "세수가 많이 들어오면 정부가 할 수 있는 건 두 가지예요."
        sentence = "추가 많이 들어오면 정부가 할 수 있는 건 두 가지"

        self.assertTrue(_sentences_are_revisions(committed, sentence))
        self.assertEqual(_sentence_output_delta(committed, sentence), "")

    def test_sentence_output_delta_keeps_korean_revision_tail_after_internal_overlap_from_log(self) -> None:
        committed = "트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런 세상에서는 기업들 딴에서의 그런 힘겨움을 끌어주기 위해서 트럼프의 정책적 방향성들을 제시할 수 있는 거고 그리고"
        sentence = "트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런 힘겨움을 끌어주기 위해서 트럼프의 정책적 방향성들을 제시할 수 있는 거고 그리고 이제 만약에 그렇게"

        self.assertTrue(_sentences_are_revisions(committed, sentence))
        self.assertEqual(_sentence_output_delta(committed, sentence), "이제 만약에 그렇게")

    def test_sentence_output_delta_trims_chinese_window_prefix_reuse_from_log(self) -> None:
        committed = "我要的是一个四合一的大份十七，小份十六，还是非常丰 边的第一顿，必须得吃这个裤带面。你们看了吗？它超级的宽，因为它很像裤带，所以它叫裤带面。我要的是一个四合一的大份儿十七，小份儿十六，还是非常丰富的。"
        sentence = "鸡蛋西红柿有剁椒，还有肉，还有土豆丁、胡萝卜丁，这儿 它很像裤带，所以它叫裤带面。我要的是一个四合一的大份儿十七，小份儿十六，还是非常丰富的。鸡蛋西红柿有剁椒，还有肉，还有土豆丁、胡萝卜丁，这儿还有点韭菜。"

        self.assertEqual(_sentence_output_delta(committed, sentence), "鸡蛋西红柿有剁椒还有肉还有土豆丁胡萝卜丁这儿还有点韭菜")

    def test_sentence_output_delta_trims_chinese_revised_prefix_before_overlap_from_log(self) -> None:
        committed = "韩国汤匙它是扁的，然后很长800块芝麻喔，它这个机器好酷喔，他们给我一点试吃。"
        sentence = "它是扁的，然后很长800块芝麻，它这个机器好酷喔，他们给我一点试吃，它感觉有去炒过耶超香的。"

        self.assertEqual(_sentence_output_delta(committed, sentence), "它感觉有去炒过耶超香的")

    def test_sentence_output_delta_trims_chinese_committed_tail_block_from_monitoring(self) -> None:
        committed = "它这个膜很结实，它是用了西北秦川的黄牛肉来制作的，就是吃着不是很柴， 在我看来，那优质就是瘦一点，对吧？然后这普通就有点肥，你看里边那肥的，吃一口啊。这膜跟刚搬进膜是一个膜，大白膜。都叫脱脱膜，脱膜。 来 你看里边那肥的，吃一口啊。这馍跟刚搬进馍是一个馍。大白馍。都叫脱脱馍。脱馍。它这个馍很结实。它是用了西北秦川的黄牛肉来制作的，就是吃着不是很柴，吃着非常的嫩的那种牛肉。"
        sentence = "它 馍跟刚拌进馍是一个馍，大白馍。都叫脱脱馍。脱馍。它这个馍很结实。它是用了西北秦川的黄牛肉来制作的，就是吃的不是很柴，吃的非常的嫩的那种牛肉。来了您的羊肉泡馍。谢谢。羊肉泡馍来了。哇，好香啊。"

        self.assertTrue(_sentences_are_revisions(committed, sentence))
        self.assertEqual(_sentence_output_delta(committed, sentence), "来了您的羊肉泡馍谢谢羊肉泡馍来了哇好香啊")

    def test_sentence_output_delta_suppresses_chinese_internal_committed_overlap_from_monitoring(self) -> None:
        committed = "漫步下号里老街巷，触摸着重庆的旧时光；再搭乘长江索道，穿梭在两江上空， 皇冠大扶梯，超多层立交桥，还有令人难忘的绝美夜景和数也数不尽的江湖美食。今天就让我们奔赴一场山城盛宴，行程与美食双双拉满，体验一下当轻轨吃进嘴里是一种什么感觉。"
        sentence = "当你看着满街霓虹点亮这座赛博山城的时候，味 山城盛宴，行程与美食双双拉满，体验一下当轻轨吃进嘴里是一种什么感觉。漫步下号里老街巷，触摸着重庆的旧时光。再搭乘长江索道，穿梭在两江上空，眼底高楼林立的错落感与重庆的老字形成了鲜明的对比。"

        self.assertEqual(_sentence_output_delta(committed, sentence), "")

    def test_sentence_output_delta_suppresses_chinese_late_internal_committed_overlap_from_monitoring(self) -> None:
        committed = "漫步下号里老街巷，触摸着重庆的旧时光；再搭乘长江索道，穿梭在两江上空， 皇冠大扶梯，超多层立交桥，还有令人难忘的绝美夜景和数也数不尽的江湖美食。今天就让我们奔赴一场山城盛宴，行程与美食双双拉满，体验一下当轻轨吃进嘴里是一种什么感觉。 当你看着满街霓虹点亮这座赛博山城的时候，味 山城盛宴，行程与美食双双拉满，体验一下当轻轨吃进嘴里是一种什么感觉。漫步下号里老街巷，触摸着重庆的旧时光。再搭乘长江索道，穿梭在两江上空，眼底高楼林立的错落感与重庆的老字形成了鲜明的对比。 一碗劲道的重庆小面，一条焦香的巫山烤鱼，一锅火辣的美蛙鱼头，重庆的每一道美食都能在你 都淋漓的错落感，与重庆的老字形成了鲜明的对比。当你看着满街霓虹点亮这座赛博山城的时候，味道晕头转向的你，才会发现乌都真正的灵魂藏在烟火弥漫的后厨中。"
        sentence = "山水有灵，十味留香， 赛博山城的时候，味道晕头转向的你，才会发现乌都真正的灵魂藏在烟火弥漫的后厨中。一碗劲道的重庆小面，一条焦香的巫山烤鱼，一锅火辣的美蛙鱼头。重庆的每一道美食都能在你饥肠辘辘的时候把你拯救回来。"

        self.assertEqual(_sentence_output_delta(committed, sentence), "")


if __name__ == "__main__":
    unittest.main()
