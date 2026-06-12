import unittest

from src.app.translation_model import MockTextTranslator, TranslationRequest, _nllb_language_code, build_text_translator


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

    def test_mock_translator_keeps_target_metadata(self) -> None:
        translator = MockTextTranslator()
        translated = translator.translate(TranslationRequest("hello", "en", "ko"))

        self.assertEqual(translated, "[mock en->ko] hello")


if __name__ == "__main__":
    unittest.main()
