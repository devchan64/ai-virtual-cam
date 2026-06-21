import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.app.dictation_pipeline_contracts import (
    ActiveSentenceCandidate,
    AudioEvidence,
    RecognitionHypothesis,
    UncommittedContext,
)
from src.app.dictation_node_sentence_candidate_commit_buffer import SentenceCandidateCommitBufferNode
from src.app.dictation_node_speech_evidence_to_stt_hypothesis import SpeechEvidenceToSttHypothesisNode
from src.app.dictation_node_stt_hypothesis_to_sentence_candidate import SttHypothesisToSentenceCandidateNode
from src.app.dictation_pipeline_settings import (
    CJK_CHAR_RANGES,
    MAX_SEGMENT_NO_SPEECH_CJK_OVERRIDE_PROB,
    MAX_SEGMENT_NO_SPEECH_PROB,
    MIN_CJK_CHARS_FOR_NO_SPEECH_OVERRIDE,
    RECENT_FINAL_EXTENSION_MIN_PREFIX_UNITS,
    RECENT_FINAL_EXTENSION_MIN_SUFFIX_UNITS,
    MIN_SEGMENT_AVG_LOGPROB,
    SEGMENT_HIGH_NO_SPEECH_OVERRIDE_LANGUAGES,
    SEGMENT_LOGPROB_CONFIDENCE_WEIGHT,
    SEGMENT_LOGPROB_SCORE_OFFSET,
    SEGMENT_LOGPROB_SCORE_SCALE,
    SEGMENT_NO_SPEECH_CONFIDENCE_WEIGHT,
    STT_CONDITION_ON_PREVIOUS_TEXT,
    STT_STREAM_AUDIO_DTYPE,
    STT_TRANSCRIBE_TASK,
    STT_WITHOUT_TIMESTAMPS,
    dictation_pipeline_policy,
    dictation_tuning_manifest,
    dictation_tuning_protocol,
)
from src.app.dictation_transcript_logic import (
    _final_sentence_diagnostic_flags,
    _normalized_text,
    _recent_final_output_delta,
    _should_stage_boundary_candidate,
    _should_suppress_delta_final,
    _should_translate_final_sentence,
)
from src.app.sentence_boundary import SentenceBoundaryResult


class FakeSttModel:
    streaming = False
    last_kwargs = None

    def transcribe(self, audio_window, **kwargs):
        del audio_window
        self.last_kwargs = kwargs
        return [SimpleNamespace(text="Hello world.", avg_logprob=-0.2, no_speech_prob=0.1)], SimpleNamespace(
            language="en"
        )


class FakeBoundaryDetector:
    backend = "fake"

    def split(self, pending_text, new_text, language="en", *, boundary_confidence=None):
        self.last_call = (pending_text, new_text, language, boundary_confidence)
        return SentenceBoundaryResult(
            completed=["Hello world."],
            pending="next",
            backend=self.backend,
            boundary_count=1,
            soft_boundary_count=0,
            end_mark_count=1,
            right_context_start_count=1,
        )


class DictationPipelineNodeTest(unittest.TestCase):
    def test_active_sentence_candidate_tracks_commit_node_state(self) -> None:
        active = ActiveSentenceCandidate()

        active.start("candidate.", forced=True, chunk_index=4)

        self.assertEqual(active.sentence, "candidate.")
        self.assertEqual(active.confirmations, 1)
        self.assertEqual(active.age, 0)
        self.assertTrue(active.forced)
        self.assertEqual(active.deferredAgeChunk, 4)
        self.assertEqual(active.deltaSuppressedChunks, 0)
        self.assertEqual(active.deltaSuppressedChunkIndex, -1)

        active.apply_buffer_entry(
            {
                "sentence": "queued.",
                "confirmations": 2,
                "age": 3,
                "forced": False,
                "deferred_age_chunk": 9,
            }
        )

        self.assertEqual(active.sentence, "queued.")
        self.assertEqual(active.confirmations, 2)
        self.assertEqual(active.age, 3)
        self.assertFalse(active.forced)
        self.assertEqual(active.deferredAgeChunk, 9)
        self.assertEqual(active.deltaSuppressedChunks, 0)
        self.assertEqual(active.deltaSuppressedChunkIndex, -1)

        active.clear()

        self.assertEqual(active.sentence, "")
        self.assertEqual(active.confirmations, 0)
        self.assertEqual(active.age, 0)
        self.assertFalse(active.forced)
        self.assertEqual(active.deferredAgeChunk, -1)
        self.assertEqual(active.deltaSuppressedChunks, 0)
        self.assertEqual(active.deltaSuppressedChunkIndex, -1)

    def test_speech_evidence_node_emits_recognition_hypothesis_contract(self) -> None:
        node = SpeechEvidenceToSttHypothesisNode(
            SimpleNamespace(
                language="en",
                beamSize=1,
                temperature=0.0,
                maxNewTokens=32,
                stepSeconds=1.0,
                windowSeconds=4.0,
            )
        )

        model = FakeSttModel()

        hypothesis = node.recognize(
            evidence=AudioEvidence(
                chunkIndex=7,
                inputDevice="test",
                sampleRate=16000,
                windowSeconds=4.0,
                stepSeconds=1.0,
                audioWindow=object(),
            ),
            model=model,
            stream_block=object(),
            committed_text="",
            pending_text="",
        )

        self.assertIsInstance(hypothesis, RecognitionHypothesis)
        self.assertEqual(hypothesis.chunkIndex, 7)
        self.assertEqual(hypothesis.language, "en")
        self.assertEqual(hypothesis.rawText, "Hello world.")
        self.assertEqual(hypothesis.deltaText, "Hello world.")
        self.assertAlmostEqual(hypothesis.segmentBoundaryConfidence, 0.91)
        self.assertIsNotNone(hypothesis.stability)
        self.assertEqual(model.last_kwargs["task"], STT_TRANSCRIBE_TASK)
        self.assertEqual(model.last_kwargs["without_timestamps"], STT_WITHOUT_TIMESTAMPS)
        self.assertEqual(model.last_kwargs["condition_on_previous_text"], STT_CONDITION_ON_PREVIOUS_TEXT)

    def test_speech_evidence_node_segment_policy_is_exported_from_pipeline_settings(self) -> None:
        policy = dictation_pipeline_policy()

        self.assertEqual(policy["stt_transcribe_task"], STT_TRANSCRIBE_TASK)
        self.assertEqual(policy["stt_without_timestamps"], STT_WITHOUT_TIMESTAMPS)
        self.assertEqual(policy["stt_condition_on_previous_text"], STT_CONDITION_ON_PREVIOUS_TEXT)
        self.assertEqual(policy["stt_stream_audio_dtype"], STT_STREAM_AUDIO_DTYPE)
        self.assertEqual(
            policy["recent_final_extension_min_prefix_units"],
            RECENT_FINAL_EXTENSION_MIN_PREFIX_UNITS,
        )
        self.assertEqual(
            policy["recent_final_extension_min_suffix_units"],
            RECENT_FINAL_EXTENSION_MIN_SUFFIX_UNITS,
        )
        self.assertEqual(policy["min_segment_avg_logprob"], MIN_SEGMENT_AVG_LOGPROB)
        self.assertEqual(policy["max_segment_no_speech_prob"], MAX_SEGMENT_NO_SPEECH_PROB)
        self.assertEqual(policy["max_segment_no_speech_cjk_override_prob"], MAX_SEGMENT_NO_SPEECH_CJK_OVERRIDE_PROB)
        self.assertEqual(policy["min_cjk_chars_for_no_speech_override"], MIN_CJK_CHARS_FOR_NO_SPEECH_OVERRIDE)
        self.assertEqual(policy["segment_logprob_score_offset"], SEGMENT_LOGPROB_SCORE_OFFSET)
        self.assertEqual(policy["segment_logprob_score_scale"], SEGMENT_LOGPROB_SCORE_SCALE)
        self.assertEqual(policy["segment_logprob_confidence_weight"], SEGMENT_LOGPROB_CONFIDENCE_WEIGHT)
        self.assertEqual(policy["segment_no_speech_confidence_weight"], SEGMENT_NO_SPEECH_CONFIDENCE_WEIGHT)
        self.assertEqual(policy["cjk_char_ranges"], CJK_CHAR_RANGES)
        self.assertEqual(
            policy["segment_high_no_speech_override_languages"],
            sorted(SEGMENT_HIGH_NO_SPEECH_OVERRIDE_LANGUAGES),
        )

    def test_lifecycle_policy_supports_benchmark_env_overrides(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "AVC_DICTATION_MAX_STAGED_SENTENCE_QUEUE": "33",
                "AVC_DICTATION_SENTENCE_CONFIRM_CHUNKS": "4",
                "AVC_DICTATION_SHORT_NO_END_FRAGMENT_UNITS": "6",
            },
        ):
            policy = dictation_pipeline_policy()

        self.assertEqual(policy["max_staged_sentence_queue"], 33)
        self.assertEqual(policy["sentence_confirm_chunks"], 4)
        self.assertEqual(policy["short_no_end_fragment_units"], 6)

    def test_tuning_manifest_documents_env_overrides_and_evidence_scope(self) -> None:
        with patch.dict("os.environ", {"AVC_DICTATION_SENTENCE_CONFIRM_CHUNKS": "5"}):
            manifest = dictation_tuning_manifest()

        by_name = {entry["name"]: entry for entry in manifest}
        self.assertEqual(by_name["SENTENCE_CONFIRM_CHUNKS"]["env"], "AVC_DICTATION_SENTENCE_CONFIRM_CHUNKS")
        self.assertEqual(by_name["SENTENCE_CONFIRM_CHUNKS"]["current"], 5)
        self.assertEqual(by_name["SENTENCE_CONFIRM_CHUNKS"]["evidence_basis"], "app-log replay benchmark")
        self.assertIn("not direct threshold source", by_name["SENTENCE_CONFIRM_CHUNKS"]["external_reference_role"])
        self.assertIn("AVC_DICTATION_*", by_name["SENTENCE_CONFIRM_CHUNKS"]["change_rule"])
        self.assertIn("CUDA benchmark evidence", by_name["SENTENCE_CONFIRM_CHUNKS"]["default_promotion_rule"])

    def test_tuning_protocol_keeps_paper_experiment_scope_explicit(self) -> None:
        protocol = dictation_tuning_protocol()

        self.assertEqual(protocol["case_source"], "app logs only")
        self.assertIn("human expected_final review", protocol["draft_rule"])
        self.assertEqual(protocol["benchmark_runtime"], "sat + cuda + float16 only")
        self.assertIn("not paper evidence", protocol["exploratory_sweep_rule"])
        self.assertEqual(protocol["paper_evidence_case_source"], "app-log-reviewed-finalization-cases")
        self.assertEqual(protocol["paper_evidence_reviewed_finalization_case_target"], 1000)
        self.assertIn("--paper-evidence", protocol["paper_evidence_rule"])
        self.assertIn("same reviewed case set", protocol["comparison_rule"])
        self.assertIn("language-specific phrase rules", protocol["forbidden_changes"])
        self.assertIn("final_f1_avg", protocol["primary_metrics"])

    def test_final_translation_policy_keeps_short_final_sentences(self) -> None:
        self.assertTrue(_should_translate_final_sentence("我喜欢这一件。", "zh"))
        self.assertTrue(_should_translate_final_sentence("耶。", "zh"))
        self.assertTrue(_should_translate_final_sentence("走吧，Go。", "zh"))
        self.assertTrue(_should_translate_final_sentence("然 后 刚 好 就 帮 我 们 穿 好", "zh"))
        self.assertTrue(_should_translate_final_sentence("OK", "zh"))

    def test_final_translation_policy_suppresses_only_non_consumable_fragments(self) -> None:
        self.assertFalse(_should_translate_final_sentence("", "zh"))
        self.assertFalse(
            _should_translate_final_sentence(
                "一二三四五六七八一二三四五六七八一二三四五六七八一二三四五六七八一二三四五六七八。",
                "zh",
            )
        )

    def test_delta_final_policy_suppresses_broken_cjk_delta_fragments(self) -> None:
        self.assertEqual(_normalized_text("这 个 川 菜 一 定 要"), "这个川菜一定要")
        self.assertTrue(
            _should_suppress_delta_final(
                "大家好，鸡肉拌牛肉拌，这个川菜一定要牛肉，牛肉拌。",
                "这 个 川 菜 一 定 要",
                "zh",
                "replaced_confirmed",
            )
        )
        self.assertTrue(
            _should_suppress_delta_final(
                "大家好，鸡肉拌牛肉拌，这个川菜一定要牛肉，牛肉拌。",
                "这个川菜一定要",
                "zh",
                "replaced_confirmed",
            )
        )

    def test_cjk_space_artifact_normalization_preserves_stageable_sentences(self) -> None:
        sentence = "如 果 你 们 要 找 吃 的 话 呢，你 们 就 可 以 到 大 众 点 评。"

        self.assertEqual(_normalized_text(sentence), "如果你们要找吃的话呢，你们就可以到大众点评。")
        self.assertTrue(_should_stage_boundary_candidate(sentence, "zh"))

    def test_recent_final_delta_recovers_meaningful_suffix_extensions(self) -> None:
        candidate, recent_source = _recent_final_output_delta(
            "来之前的时候，我查了一下这个白象居，它现在是一个网红居民楼嘛。",
            ("来之前的时候，我查了一下这个白象居，它。",),
            "zh",
        )

        self.assertEqual(candidate, "现在是一个网红居民楼嘛。")
        self.assertEqual(recent_source, "来之前的时候，我查了一下这个白象居，它。")

    def test_recent_final_delta_recovers_short_cjk_object_extension(self) -> None:
        candidate, recent_source = _recent_final_output_delta(
            "这里进来，这里就是它的厕所。",
            ("这里进来，这里就是。",),
            "zh",
        )

        self.assertEqual(candidate, "它的厕所。")
        self.assertEqual(recent_source, "这里进来，这里就是。")

    def test_recent_final_delta_keeps_short_suffix_corrections_suppressed(self) -> None:
        candidate, recent_source = _recent_final_output_delta(
            "所以还是有很多小摊贩在摆摊。",
            ("所以还是有很多小摊贩在摆。",),
            "zh",
        )

        self.assertEqual(candidate, "")
        self.assertEqual(recent_source, "所以还是有很多小摊贩在摆。")

    def test_short_cjk_without_end_marker_is_not_stageable(self) -> None:
        self.assertIn(
            "short_no_end_fragment",
            _final_sentence_diagnostic_flags("它对面的这一家", "zh"),
        )
        self.assertFalse(_should_stage_boundary_candidate("它对面的这一家", "zh"))

    def test_short_cjk_with_end_marker_remains_stageable(self) -> None:
        self.assertNotIn(
            "short_no_end_fragment",
            _final_sentence_diagnostic_flags("哇，看起来就很好吃。", "zh"),
        )
        self.assertTrue(_should_stage_boundary_candidate("哇，看起来就很好吃。", "zh"))

    def test_hypothesis_candidate_node_preserves_boundary_contract(self) -> None:
        detector = FakeBoundaryDetector()
        node = SttHypothesisToSentenceCandidateNode(lambda language: detector)

        candidate_set = node.interpret(
            hypothesis=RecognitionHypothesis(
                chunkIndex=3,
                language="en",
                rawText="Hello world. next",
                windowText="Hello world. next",
                stableText="Hello world. next",
                deltaText="Hello world. next",
                boundaryConfidence=0.7,
            ),
            context=UncommittedContext(committedText="", pendingText=""),
        )

        self.assertEqual(candidate_set.completedCandidates, ("Hello world.",))
        self.assertEqual(candidate_set.pendingTail, "next")
        self.assertEqual(candidate_set.boundarySignals["boundary_backend"], "fake")
        self.assertEqual(candidate_set.boundarySignals["boundary_confidence"], 0.7)
        self.assertEqual(detector.last_call, ("", "Hello world. next", "en", 0.7))

    def test_commit_buffer_promotes_created_order_candidates(self) -> None:
        metrics: dict[str, int] = {}
        states: dict[str, int] = {}

        def count_metric(name: str, amount: int = 1) -> None:
            metrics[name] = metrics.get(name, 0) + amount

        def count_state(name: str, amount: int = 1) -> None:
            states[name] = states.get(name, 0) + amount

        node = SentenceCandidateCommitBufferNode(max_size=2)
        stable = SimpleNamespace(
            stable_internal_ratio=1.0,
            stable_internal_chars=10,
            stable_overlap_source="prefix",
        )

        node.enqueue_or_revision(
            candidate="first sentence.",
            forced=False,
            chunk_index=1,
            stable_analysis=stable,
            count_metric=count_metric,
            count_segment_state=count_state,
        )
        node.enqueue_or_revision(
            candidate="second sentence.",
            forced=True,
            chunk_index=2,
            stable_analysis=stable,
            count_metric=count_metric,
            count_segment_state=count_state,
        )

        self.assertEqual(len(node), 2)
        promoted = node.promote_if_idle(
            chunk_index=3,
            count_metric=count_metric,
            count_segment_state=count_state,
        )

        self.assertTrue(promoted)
        self.assertEqual(node.active.sentence, "first sentence.")
        self.assertEqual(node.active.age, 2)
        self.assertEqual(node.active.deferredAgeChunk, 1)
        self.assertEqual(len(node), 1)
        self.assertEqual(metrics["stage_queue_enqueue"], 2)
        self.assertEqual(metrics["stage_queue_promote"], 1)

    def test_commit_buffer_promoted_queue_candidate_ages_from_enqueue_chunk(self) -> None:
        metrics: dict[str, int] = {}
        states: dict[str, int] = {}

        def count_metric(name: str, amount: int = 1) -> None:
            metrics[name] = metrics.get(name, 0) + amount

        def count_state(name: str, amount: int = 1) -> None:
            states[name] = states.get(name, 0) + amount

        node = SentenceCandidateCommitBufferNode(max_size=2)
        stable = SimpleNamespace(
            stable_internal_ratio=1.0,
            stable_internal_chars=10,
            stable_overlap_source="prefix",
        )

        node.enqueue_or_revision(
            candidate="地铁怎么样的感觉？",
            forced=False,
            chunk_index=20,
            stable_analysis=stable,
            count_metric=count_metric,
            count_segment_state=count_state,
        )

        promoted = node.promote_if_idle(
            chunk_index=25,
            count_metric=count_metric,
            count_segment_state=count_state,
        )

        self.assertTrue(promoted)
        self.assertEqual(node.active.sentence, "地铁怎么样的感觉？")
        self.assertEqual(node.active.age, 5)
        self.assertEqual(node.active.deferredAgeChunk, 20)
        self.assertEqual(metrics["stage_queue_promote"], 1)

    def test_commit_buffer_preserves_revised_queue_chunk_on_promotion(self) -> None:
        metrics: dict[str, int] = {}
        states: dict[str, int] = {}

        def count_metric(name: str, amount: int = 1) -> None:
            metrics[name] = metrics.get(name, 0) + amount

        def count_state(name: str, amount: int = 1) -> None:
            states[name] = states.get(name, 0) + amount

        node = SentenceCandidateCommitBufferNode(max_size=2)
        stable = SimpleNamespace(
            stable_internal_ratio=1.0,
            stable_internal_chars=20,
            stable_overlap_source="prefix",
        )

        node.enqueue_or_revision(
            candidate="可以下一个就是裤子啦。",
            forced=False,
            chunk_index=10,
            stable_analysis=stable,
            count_metric=count_metric,
            count_segment_state=count_state,
        )
        node.enqueue_or_revision(
            candidate="可以下一个就是裤子啦。",
            forced=False,
            chunk_index=11,
            stable_analysis=stable,
            count_metric=count_metric,
            count_segment_state=count_state,
        )

        promoted = node.promote_if_idle(
            chunk_index=12,
            count_metric=count_metric,
            count_segment_state=count_state,
        )

        self.assertTrue(promoted)
        self.assertEqual(node.active.sentence, "可以下一个就是裤子啦。")
        self.assertEqual(node.active.confirmations, 2)
        self.assertEqual(node.active.age, 1)
        self.assertEqual(node.active.deferredAgeChunk, 11)
        self.assertEqual(metrics["stage_queue_revision"], 1)


if __name__ == "__main__":
    unittest.main()
