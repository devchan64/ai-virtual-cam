import unittest

from scripts.config.i18n import (
    FALLBACK_LANGUAGE,
    LANG_PACK_DIR,
    SUPPORTED_LANGUAGES,
    language_pack_paths,
    load_language_pack,
    read_flat_yaml,
    validate_language_pack_keys,
)


class ConfigI18nTest(unittest.TestCase):
    def test_supported_language_packs_exist(self) -> None:
        paths = language_pack_paths()

        for language in SUPPORTED_LANGUAGES:
            self.assertIn(language, paths)
            self.assertTrue(paths[language].exists())

    def test_language_pack_keys_match_fallback_language(self) -> None:
        mismatches = validate_language_pack_keys(FALLBACK_LANGUAGE)

        self.assertEqual(mismatches, {})

    def test_load_language_pack_uses_fallback_and_selected_language(self) -> None:
        english = read_flat_yaml(LANG_PACK_DIR / "config-gui.en.yaml")
        korean = read_flat_yaml(LANG_PACK_DIR / "config-gui.ko.yaml")

        loaded = load_language_pack("ko")

        self.assertEqual(loaded["button.save"], korean["button.save"])
        self.assertEqual(loaded["label.whisper_sentence_boundary_model_zh"], korean["label.whisper_sentence_boundary_model_zh"])
        self.assertEqual(set(english), set(loaded))

    def test_unknown_language_uses_default_language(self) -> None:
        self.assertEqual(load_language_pack("unknown")["button.save"], load_language_pack("ko")["button.save"])


if __name__ == "__main__":
    unittest.main()
