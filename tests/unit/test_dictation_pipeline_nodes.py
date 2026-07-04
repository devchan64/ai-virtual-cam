import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.app.dictation.pipeline_chunk_interpreter import process_chunk_sentence_flow
from src.app.dictation.pipeline_contracts import (
    ActiveSentenceCandidate,
    AudioEvidence,
    RecognitionHypothesis,
    UncommittedContext,
)
from src.app.dictation.node_sentence_candidate_commit_buffer import SentenceCandidateCommitBufferNode
from src.app.dictation.node_speech_evidence_to_stt_hypothesis import SpeechEvidenceToSttHypothesisNode
from src.app.dictation.node_stt_hypothesis_to_sentence_candidate import SttHypothesisToSentenceCandidateNode
from src.app.dictation.pipeline_settings import (
    AGED_QUEUE_BACKLOG_PROMOTION_EXTRA_AGE,
    AGED_QUEUE_BACKLOG_PROMOTION_MIN,
    CJK_CHAR_RANGES,
    MAX_SEGMENT_NO_SPEECH_CJK_OVERRIDE_PROB,
    MAX_SEGMENT_NO_SPEECH_PROB,
    MIN_CJK_CHARS_FOR_NO_SPEECH_OVERRIDE,
    RECENT_FINAL_EXTENSION_MIN_PREFIX_UNITS,
    RECENT_FINAL_EXTENSION_MIN_SUFFIX_UNITS,
    SHORT_CJK_CONFIRM_EXTRA_CHUNKS,
    MIN_SEGMENT_AVG_LOGPROB,
    SEGMENT_HIGH_NO_SPEECH_OVERRIDE_LANGUAGES,
    SEGMENT_LOGPROB_CONFIDENCE_WEIGHT,
    SEGMENT_LOGPROB_SCORE_OFFSET,
    SEGMENT_LOGPROB_SCORE_SCALE,
    SEGMENT_NO_SPEECH_CONFIDENCE_WEIGHT,
    STAGED_QUEUE_MAX_PROMOTION_AGE_CHUNKS,
    STT_CONDITION_ON_PREVIOUS_TEXT,
    STT_STREAM_AUDIO_DTYPE,
    STT_TRANSCRIBE_TASK,
    STT_WITHOUT_TIMESTAMPS,
    dictation_pipeline_policy,
    dictation_tuning_manifest,
    dictation_tuning_protocol,
)
from src.app.dictation_core.dictation_transcript_logic import (
    _prefer_sentence_revision,
    _replacement_decision_reason,
    _strip_prior_pending_prefix_from_final,
    _strip_prior_pending_prefix_revision,
    _should_translate_final_sentence,
)
from src.app.dictation_core.sentence_boundary import SentenceBoundaryResult


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
        self.assertEqual(policy["short_cjk_confirm_extra_chunks"], SHORT_CJK_CONFIRM_EXTRA_CHUNKS)
        self.assertEqual(policy["cjk_char_ranges"], CJK_CHAR_RANGES)
        self.assertEqual(
            policy["segment_high_no_speech_override_languages"],
            sorted(SEGMENT_HIGH_NO_SPEECH_OVERRIDE_LANGUAGES),
        )
        self.assertEqual(
            policy["staged_queue_max_promotion_age_chunks"],
            STAGED_QUEUE_MAX_PROMOTION_AGE_CHUNKS,
        )
        self.assertEqual(
            policy["aged_queue_backlog_promotion_min"],
            AGED_QUEUE_BACKLOG_PROMOTION_MIN,
        )
        self.assertEqual(
            policy["aged_queue_backlog_promotion_extra_age"],
            AGED_QUEUE_BACKLOG_PROMOTION_EXTRA_AGE,
        )

    def test_lifecycle_policy_supports_benchmark_env_overrides(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "AVC_DICTATION_MAX_STAGED_SENTENCE_QUEUE": "33",
                "AVC_DICTATION_SENTENCE_CONFIRM_CHUNKS": "4",
                "AVC_DICTATION_SHORT_NO_END_FRAGMENT_UNITS": "6",
                "AVC_DICTATION_SHORT_CJK_CONFIRM_EXTRA_CHUNKS": "2",
                "AVC_DICTATION_LONG_NO_END_REPLACEMENT_EARLY_AGE_MIN_UNITS": "11",
                "AVC_DICTATION_STAGED_QUEUE_MAX_PROMOTION_AGE_CHUNKS": "9",
                "AVC_DICTATION_AGED_QUEUE_BACKLOG_PROMOTION_MIN": "4",
                "AVC_DICTATION_AGED_QUEUE_BACKLOG_PROMOTION_EXTRA_AGE": "2",
            },
        ):
            policy = dictation_pipeline_policy()

        self.assertEqual(policy["max_staged_sentence_queue"], 33)
        self.assertEqual(policy["staged_queue_max_promotion_age_chunks"], 9)
        self.assertEqual(policy["sentence_confirm_chunks"], 4)
        self.assertEqual(policy["short_no_end_fragment_units"], 6)
        self.assertEqual(policy["short_cjk_confirm_extra_chunks"], 2)
        self.assertEqual(policy["long_no_end_replacement_early_age_min_units"], 11)
        self.assertEqual(policy["aged_queue_backlog_promotion_min"], 4)
        self.assertEqual(policy["aged_queue_backlog_promotion_extra_age"], 2)

    def test_replacement_policy_ages_long_non_cjk_no_end_stage_one_chunk_early(self) -> None:
        reason = _replacement_decision_reason(
            "so you know I was watching this graph for a while and I said maybe people were still asking the wrong question",
            "now people are asking a different question.",
            staged_confirmations=1,
            staged_forced=False,
            staged_age=2,
            sentence_finalize_age=3,
        )

        self.assertEqual(reason, "aged")

    def test_no_text_chunk_ages_closed_stage_before_stale_suppression(self) -> None:
        suppressed_calls: list[int] = []

        result = process_chunk_sentence_flow(
            candidate_node=SimpleNamespace(),
            hypothesis=SimpleNamespace(),
            detected="zh",
            text="",
            chunk_index=7,
            committed_text="",
            pending_transcript_text="",
            pending_chunks=0,
            no_text_stage_skip_chunks=0,
            active_stage_sentence="这是完整句子。",
            staged_queue_sentences=(),
            window_text="这是完整句子。",
            stable_text="这是完整句子。",
            count_metric=lambda *_args, **_kwargs: None,
            count_segment_state=lambda *_args, **_kwargs: None,
            stage_completed_sentence=lambda *args, **kwargs: [],
            finalize_right_context_staged_sentences=lambda *_args, **_kwargs: [],
            age_staged_sentence=lambda *_args, **_kwargs: [(3, "这是完整句子。")],
            suppress_stale_no_text_stage=lambda _detected, skip_chunks: suppressed_calls.append(skip_chunks) or skip_chunks,
            consume_committed_prefix=lambda pending, _produced: pending,
            emit_status=lambda _status: None,
        )

        self.assertEqual(result.final_segments, [(3, "这是完整句子。")])
        self.assertEqual(result.no_text_stage_skip_chunks, 0)
        self.assertEqual(suppressed_calls, [])

    def test_no_text_chunk_keeps_non_cjk_stage_on_stale_path(self) -> None:
        suppressed_calls: list[int] = []
        age_calls: list[str] = []

        result = process_chunk_sentence_flow(
            candidate_node=SimpleNamespace(),
            hypothesis=SimpleNamespace(),
            detected="en",
            text="",
            chunk_index=9,
            committed_text="",
            pending_transcript_text="",
            pending_chunks=0,
            no_text_stage_skip_chunks=0,
            active_stage_sentence="This is a complete sentence.",
            staged_queue_sentences=(),
            window_text="This is a complete sentence.",
            stable_text="This is a complete sentence.",
            count_metric=lambda *_args, **_kwargs: None,
            count_segment_state=lambda *_args, **_kwargs: None,
            stage_completed_sentence=lambda *args, **kwargs: [],
            finalize_right_context_staged_sentences=lambda *_args, **_kwargs: [],
            age_staged_sentence=lambda *_args, **_kwargs: age_calls.append("called") or [(5, "This is a complete sentence.")],
            suppress_stale_no_text_stage=lambda _detected, skip_chunks: suppressed_calls.append(skip_chunks) or skip_chunks,
            consume_committed_prefix=lambda pending, _produced: pending,
            emit_status=lambda _status: None,
        )

        self.assertEqual(result.final_segments, [])
        self.assertEqual(result.no_text_stage_skip_chunks, 0)
        self.assertEqual(age_calls, [])
        self.assertEqual(suppressed_calls, [])

    def test_commit_buffer_drops_stale_queued_candidate_before_promotion(self) -> None:
        node = SentenceCandidateCommitBufferNode(max_size=4)
        metrics: dict[str, int] = {}

        def count_metric(name: str, amount: int = 1) -> None:
            metrics[name] = metrics.get(name, 0) + amount

        stable_analysis = SimpleNamespace(
            stable_internal_ratio=0.0,
            stable_internal_chars=0,
            stable_overlap_source="none",
        )
        node.enqueue_or_revision(
            candidate="stale queued sentence.",
            forced=False,
            chunk_index=1,
            stable_analysis=stable_analysis,
            count_metric=count_metric,
            count_segment_state=count_metric,
        )
        node.enqueue_or_revision(
            candidate="fresh queued sentence.",
            forced=False,
            chunk_index=8,
            stable_analysis=stable_analysis,
            count_metric=count_metric,
            count_segment_state=count_metric,
        )

        promoted = node.promote_if_idle(
            chunk_index=10,
            max_promotion_age_chunks=5,
            count_metric=count_metric,
            count_segment_state=count_metric,
        )

        self.assertTrue(promoted)
        self.assertEqual(node.active.sentence, "fresh queued sentence.")
        self.assertEqual(metrics["stage_queue_stale_promote_suppressed"], 1)
        self.assertEqual(metrics["stage_queue_promote"], 1)

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

    def test_mixed_latin_cjk_prefix_growth_keeps_longer_revision(self) -> None:
        preferred = _prefer_sentence_revision(
            "我们最后一天想说来圣水洞这边晃晃，因为妹妹想要买的东西在圣水洞这边的Beaker有，然后呢。",
            "我们最后一天想说来圣水洞这边晃晃，因为妹妹想要买的东西在圣水洞这边的Beaker有。",
        )

        self.assertEqual(
            preferred,
            "我们最后一天想说来圣水洞这边晃晃，因为妹妹想要买的东西在圣水洞这边的Beaker有，然后呢。",
        )

    def test_prior_pending_prefix_keeps_normal_continuation(self) -> None:
        candidate = _strip_prior_pending_prefix_revision(
            "",
            "I went to the store.",
            "I went to",
        )

        self.assertEqual(candidate, "I went to the store.")

    def test_prior_pending_prefix_strips_repeated_accumulation_suffix(self) -> None:
        prior_pending = (
            "원래 삼성이 2등을 했을 거라고 다들 예측했는데 "
            "원래 삼성이 2등을 했을 거라고 다들 예측했는데 "
            "미세한 차이로 SMIC가"
        )
        candidate = _strip_prior_pending_prefix_revision(
            "",
            prior_pending + " 원래 삼성이 2등을 했을 거라고 다들 예측했는데 미세한 차이로 SMIC가 2등을 했어요.",
            prior_pending,
        )

        self.assertEqual(candidate, "원래 삼성이 2등을 했을 거라고 다들 예측했는데 미세한 차이로 SMIC가 2등을 했어요.")

    def test_prior_pending_prefix_strips_final_surface_prefix(self) -> None:
        final = _strip_prior_pending_prefix_from_final(
            "매출액만 보면 근데 이제 뭐 수익률이나 원래 삼성이 2등을 했을 거라고 다들 예측했는데 미세한 차이로 SMIC가 2등을 했어요.",
            "매출액만 보면 근데 이제 뭐 수익률이나",
        )

        self.assertEqual(final, "원래 삼성이 2등을 했을 거라고 다들 예측했는데 미세한 차이로 SMIC가 2등을 했어요.")

    def test_prior_pending_prefix_does_not_strip_unfinished_final_suffix(self) -> None:
        final = _strip_prior_pending_prefix_from_final(
            "I went to the store",
            "I went to",
        )

        self.assertEqual(final, "I went to the store")

    def test_cjk_revision_keeps_longer_tail_when_prefix_is_same(self) -> None:
        preferred = _prefer_sentence_revision(
            "我的里面还有小熊猫，小浣熊，加一些豆芽菜。",
            "我的里面还有小熊猫，小浣熊，加一些豆芽。",
        )

        self.assertEqual(preferred, "我的里面还有小熊猫，小浣熊，加一些豆芽菜。")

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
            max_promotion_age_chunks=99,
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
            max_promotion_age_chunks=99,
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
            max_promotion_age_chunks=99,
            count_metric=count_metric,
            count_segment_state=count_state,
        )

        self.assertTrue(promoted)
        self.assertEqual(node.active.sentence, "可以下一个就是裤子啦。")
        self.assertEqual(node.active.confirmations, 2)
        self.assertEqual(node.active.age, 1)
        self.assertEqual(node.active.deferredAgeChunk, 11)
        self.assertEqual(metrics["stage_queue_revision"], 1)

    def test_commit_buffer_suppresses_queue_revision_when_token_sentence_would_reset_age(self) -> None:
        metrics: dict[str, int] = {}
        states: dict[str, int] = {}

        def count_metric(name: str, amount: int = 1) -> None:
            metrics[name] = metrics.get(name, 0) + amount

        def count_state(name: str, amount: int = 1) -> None:
            states[name] = states.get(name, 0) + amount

        node = SentenceCandidateCommitBufferNode(max_size=4)
        stable = SimpleNamespace(
            stable_internal_ratio=0.0,
            stable_internal_chars=0,
            stable_overlap_source="none",
        )

        node.enqueue_or_revision(
            candidate="old queued token sentence.",
            forced=False,
            chunk_index=10,
            stable_analysis=stable,
            count_metric=count_metric,
            count_segment_state=count_state,
        )
        with (
            patch("src.app.dictation.node_sentence_candidate_commit_buffer._sentences_are_revisions", return_value=True),
            patch("src.app.dictation.node_sentence_candidate_commit_buffer._prefer_sentence_revision", return_value="new token sentence."),
            patch("src.app.dictation.node_sentence_candidate_commit_buffer._should_reset_revision_age", return_value=True),
        ):
            node.enqueue_or_revision(
                candidate="new token sentence.",
                forced=False,
                chunk_index=11,
                stable_analysis=stable,
                count_metric=count_metric,
                count_segment_state=count_state,
            )

        self.assertEqual(node.queued_sentences(), ("old queued token sentence.",))
        self.assertEqual(metrics["stage_queue_revision_token_sentence_deferred"], 1)
        self.assertEqual(metrics["stage_queue_enqueue"], 1)
        self.assertNotIn("stage_queue_revision", metrics)

    def test_commit_buffer_does_not_preempt_active_final_with_weak_queue_revision(self) -> None:
        metrics: dict[str, int] = {}
        states: dict[str, int] = {}

        def count_metric(name: str, amount: int = 1) -> None:
            metrics[name] = metrics.get(name, 0) + amount

        def count_state(name: str, amount: int = 1) -> None:
            states[name] = states.get(name, 0) + amount

        node = SentenceCandidateCommitBufferNode(max_size=4)
        node.active.start("short fragment.", forced=False, chunk_index=10)
        node.active.confirmations = 3
        node.active.age = 3
        stable = SimpleNamespace(
            stable_internal_ratio=0.0,
            stable_internal_chars=0,
            stable_overlap_source="none",
        )
        node.enqueue_or_revision(
            candidate="short fragment with stable tail.",
            forced=False,
            chunk_index=11,
            stable_analysis=stable,
            count_metric=count_metric,
            count_segment_state=count_state,
        )

        with (
            patch("src.app.dictation.node_sentence_candidate_commit_buffer._sentences_are_revisions", return_value=True),
            patch(
                "src.app.dictation.node_sentence_candidate_commit_buffer._prefer_sentence_revision",
                return_value="short fragment with stable tail.",
            ),
        ):
            deferred = node.prefer_queued_revision_for_active(
                chunk_index=12,
                max_promotion_age_chunks=8,
                count_metric=count_metric,
                count_segment_state=count_state,
            )

        self.assertFalse(deferred)
        self.assertEqual(node.active.sentence, "short fragment.")
        self.assertEqual(node.queued_sentences(), ("short fragment with stable tail.",))
        self.assertEqual(metrics["stage_queue_revision_preempt_deferred"], 1)
        self.assertNotIn("stage_finalize_deferred_for_queue_revision", metrics)
        self.assertNotIn("stage_revision", metrics)
        self.assertNotIn("revised", states)

    def test_commit_buffer_does_not_preempt_active_final_with_weak_cjk_queue_revision(self) -> None:
        metrics: dict[str, int] = {}
        states: dict[str, int] = {}

        def count_metric(name: str, amount: int = 1) -> None:
            metrics[name] = metrics.get(name, 0) + amount

        def count_state(name: str, amount: int = 1) -> None:
            states[name] = states.get(name, 0) + amount

        node = SentenceCandidateCommitBufferNode(max_size=4)
        node.active.start("晚上民众的部分你自己去我要。", forced=False, chunk_index=737)
        node.active.confirmations = 3
        node.active.age = 3
        stable = SimpleNamespace(
            stable_internal_ratio=0.0,
            stable_internal_chars=0,
            stable_overlap_source="none",
        )
        node.enqueue_or_revision(
            candidate="你自己去，我要去饭店休息。",
            forced=False,
            chunk_index=737,
            stable_analysis=stable,
            count_metric=count_metric,
            count_segment_state=count_state,
        )

        deferred = node.prefer_queued_revision_for_active(
            chunk_index=737,
            max_promotion_age_chunks=8,
            count_metric=count_metric,
            count_segment_state=count_state,
        )

        self.assertFalse(deferred)
        self.assertEqual(node.active.sentence, "晚上民众的部分你自己去我要。")
        self.assertEqual(node.queued_sentences(), ("你自己去，我要去饭店休息。",))
        self.assertEqual(metrics["stage_queue_revision_preempt_deferred"], 1)
        self.assertNotIn("stage_finalize_deferred_for_queue_revision", metrics)
        self.assertNotIn("stage_revision", metrics)
        self.assertNotIn("revised", states)

    def test_commit_buffer_drops_stale_queued_revision_before_active_final(self) -> None:
        metrics: dict[str, int] = {}
        states: dict[str, int] = {}

        def count_metric(name: str, amount: int = 1) -> None:
            metrics[name] = metrics.get(name, 0) + amount

        def count_state(name: str, amount: int = 1) -> None:
            states[name] = states.get(name, 0) + amount

        node = SentenceCandidateCommitBufferNode(max_size=4)
        node.active.start("short fragment.", forced=False, chunk_index=10)
        node.active.confirmations = 3
        node.active.age = 3
        stable = SimpleNamespace(
            stable_internal_ratio=0.0,
            stable_internal_chars=0,
            stable_overlap_source="none",
        )
        node.enqueue_or_revision(
            candidate="short fragment with stable tail.",
            forced=False,
            chunk_index=1,
            stable_analysis=stable,
            count_metric=count_metric,
            count_segment_state=count_state,
        )

        with (
            patch("src.app.dictation.node_sentence_candidate_commit_buffer._sentences_are_revisions", return_value=True),
            patch(
                "src.app.dictation.node_sentence_candidate_commit_buffer._prefer_sentence_revision",
                return_value="short fragment with stable tail.",
            ),
        ):
            deferred = node.prefer_queued_revision_for_active(
                chunk_index=12,
                max_promotion_age_chunks=8,
                count_metric=count_metric,
                count_segment_state=count_state,
            )

        self.assertFalse(deferred)
        self.assertEqual(node.active.sentence, "short fragment.")
        self.assertEqual(len(node), 0)
        self.assertEqual(metrics["stage_queue_stale_promote_suppressed"], 1)
        self.assertNotIn("stage_finalize_deferred_for_queue_revision", metrics)
        self.assertEqual(states["suppressed"], 1)

if __name__ == "__main__":
    unittest.main()
