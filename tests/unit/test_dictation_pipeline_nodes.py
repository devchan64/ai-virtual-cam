import unittest
from types import SimpleNamespace

from src.app.dictation_pipeline_contracts import (
    ActiveSentenceCandidate,
    AudioEvidence,
    RecognitionHypothesis,
    UncommittedContext,
)
from src.app.dictation_node_sentence_candidate_commit_buffer import SentenceCandidateCommitBufferNode
from src.app.dictation_node_speech_evidence_to_stt_hypothesis import SpeechEvidenceToSttHypothesisNode
from src.app.dictation_node_stt_hypothesis_to_sentence_candidate import SttHypothesisToSentenceCandidateNode
from src.app.sentence_boundary import SentenceBoundaryResult


class FakeSttModel:
    streaming = False

    def transcribe(self, audio_window, **kwargs):
        del audio_window, kwargs
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

        active.clear()

        self.assertEqual(active.sentence, "")
        self.assertEqual(active.confirmations, 0)
        self.assertEqual(active.age, 0)
        self.assertFalse(active.forced)
        self.assertEqual(active.deferredAgeChunk, -1)

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

        hypothesis = node.recognize(
            evidence=AudioEvidence(
                chunkIndex=7,
                inputDevice="test",
                sampleRate=16000,
                windowSeconds=4.0,
                stepSeconds=1.0,
                audioWindow=object(),
            ),
            model=FakeSttModel(),
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
        self.assertEqual(len(node), 1)
        self.assertEqual(metrics["stage_queue_enqueue"], 2)
        self.assertEqual(metrics["stage_queue_promote"], 1)


if __name__ == "__main__":
    unittest.main()
