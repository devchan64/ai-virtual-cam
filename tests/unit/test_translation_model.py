import unittest

from src.app.translation_model import (
    MockTextTranslator,
    TranslationRequest,
    _nllb_language_code,
    _torch_cuda_is_usable_for_current_gpu,
    _translation_failure_detail,
    _validate_generation_int,
    _validate_torch_cuda_supports_current_gpu,
    build_text_translator,
)


class _FakeCuda:
    def __init__(self, available=True, capability=(12, 0), arches=None, name="NVIDIA GeForce RTX 5070 Laptop GPU") -> None:
        self._available = available
        self._capability = capability
        self._arches = arches or ["sm_50", "sm_60", "sm_70", "sm_75", "sm_80", "sm_86", "sm_90"]
        self._name = name

    def is_available(self):
        return self._available

    def get_device_capability(self):
        return self._capability

    def get_arch_list(self):
        return self._arches

    def get_device_name(self):
        return self._name


class _FakeTorch:
    def __init__(self, cuda):
        self.cuda = cuda


class TranslationModelTest(unittest.TestCase):
    def test_nllb_language_codes_cover_supported_targets(self) -> None:
        self.assertEqual(_nllb_language_code("en"), "eng_Latn")
        self.assertEqual(_nllb_language_code("ko"), "kor_Hang")
        self.assertEqual(_nllb_language_code("zh"), "zho_Hans")

    def test_nllb_rejects_unsupported_language(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "en/ko/zh"):
            _nllb_language_code("ja")

    def test_whisper_backend_uses_whisper_translate_path(self) -> None:
        self.assertIsNone(build_text_translator("whisper", "unused", "cpu", "float32"))

    def test_explicit_cuda_rejects_unsupported_gpu_architecture(self) -> None:
        torch = _FakeTorch(_FakeCuda(capability=(12, 0), arches=["sm_80", "sm_86", "sm_90"]))

        with self.assertRaisesRegex(RuntimeError, "PyTorch/CUDA 빌드"):
            _validate_torch_cuda_supports_current_gpu(torch)

    def test_auto_runtime_options_are_rejected(self) -> None:
        torch = _FakeTorch(_FakeCuda(capability=(8, 0), arches=["sm_80"]))

        with self.assertRaisesRegex(RuntimeError, "translationDevice=auto"):
            from src.app.translation_model import NllbTransformersTranslator

            NllbTransformersTranslator._resolve_device(torch, "auto")
        with self.assertRaisesRegex(RuntimeError, "translationComputeType=auto"):
            from src.app.translation_model import NllbTransformersTranslator

            NllbTransformersTranslator._resolve_dtype(torch, "auto", "cuda")

    def test_cuda_usability_reports_false_when_gpu_architecture_is_unsupported(self) -> None:
        torch = _FakeTorch(_FakeCuda(capability=(12, 0), arches=["sm_80", "sm_86", "sm_90"]))

        self.assertFalse(_torch_cuda_is_usable_for_current_gpu(torch))

    def test_cuda_kernel_error_includes_retry_guidance(self) -> None:
        detail = _translation_failure_detail(
            RuntimeError("CUDA error: no kernel image is available for execution on the device"),
            model_name="facebook/nllb-200-distilled-600M",
            device="cuda",
            resolved_device="cuda",
            compute_type="float16",
            source_language="ko",
            target_language="zh",
        )

        self.assertIn("translationDevice=cuda", detail)
        self.assertIn("translationComputeType=float16", detail)
        self.assertIn("현재 GPU를 지원하는 torch/CUDA 빌드", detail)

    def test_translation_generation_options_are_validated(self) -> None:
        self.assertEqual(_validate_generation_int("test.option", 1, 1, 8), 1)
        with self.assertRaisesRegex(RuntimeError, "test.option"):
            _validate_generation_int("test.option", 0, 1, 8)

    def test_mock_translator_keeps_target_metadata(self) -> None:
        translator = MockTextTranslator()
        translated = translator.translate(TranslationRequest("hello", "en", "ko"))

        self.assertEqual(translated, "[mock en->ko] hello")


if __name__ == "__main__":
    unittest.main()
