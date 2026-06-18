import unittest
from types import SimpleNamespace

from src.app.dictation_pipeline_contracts import AudioEvidence, RecognitionHypothesis, UncommittedContext
from src.app.dictation_pipeline_nodes import (
    SentenceCandidateCommitBufferNode,
    SpeechEvidenceToSttHypothesisNode,
    SttHypothesisToSentenceCandidateNode,
)
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
            accepted_segment_texts=lambda segments: ([segment.text for segment in segments], [], 0.8),
            committed_text="",
            pending_text="",
        )

        self.assertIsInstance(hypothesis, RecognitionHypothesis)
        self.assertEqual(hypothesis.chunkIndex, 7)
        self.assertEqual(hypothesis.language, "en")
        self.assertEqual(hypothesis.rawText, "Hello world.")
        self.assertEqual(hypothesis.deltaText, "Hello world.")
        self.assertEqual(hypothesis.segmentBoundaryConfidence, 0.8)
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
            active_sentence="",
            chunk_index=3,
            count_metric=count_metric,
            count_segment_state=count_state,
        )

        self.assertEqual(promoted["sentence"], "first sentence.")
        self.assertEqual(len(node), 1)
        self.assertEqual(metrics["stage_queue_enqueue"], 2)
        self.assertEqual(metrics["stage_queue_promote"], 1)


if __name__ == "__main__":
    unittest.main()
