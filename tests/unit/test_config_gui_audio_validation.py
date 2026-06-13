import contextlib
import importlib
import io
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_GUI_PATH = REPO_ROOT / "scripts" / "config" / "create-config-gui.py"


def _load_config_gui_module():
    spec = importlib.util.spec_from_file_location("create_config_gui", CONFIG_GUI_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load create-config-gui.py")
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, {"cv2": types.SimpleNamespace(), "numpy": types.SimpleNamespace()}):
        spec.loader.exec_module(module)
    return module


class ConfigGuiAudioValidationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_config_gui_module()
        cls.audio_devices = importlib.import_module("scripts.config.audio_devices")


    def test_whisper_tab_i18n_keys_exist_for_korean_and_english(self) -> None:
        source = (REPO_ROOT / "scripts" / "config" / "whisper_tab.py").read_text(encoding="utf-8")
        import re
        keys = set(re.findall(r'"((?:label|hint|button)\.whisper[^"]+)"', source))
        self.assertGreater(len(keys), 20)

        for lang in ("ko", "en"):
            pack = self.module._read_flat_yaml(self.module.LANG_PACK_DIR / f"config-gui.{lang}.yaml")
            missing = sorted(key for key in keys if key not in pack)
            self.assertEqual(missing, [], f"missing Whisper i18n keys for {lang}")

    def test_resolve_and_validate_audio_runtime_devices_maps_display_values(self) -> None:
        with mock.patch.object(self.audio_devices.platform, "system", return_value="Linux"), mock.patch.object(
            self.audio_devices,
            "_pactl_short_entries",
            side_effect=lambda kind: [
                ("1", "alsa_input.usb-mic", "module"),
            ]
            if kind == "source"
            else [
                ("2", "ai-virtual-cam", "module"),
            ],
        ):
            raw_input, raw_output = self.audio_devices._resolve_and_validate_audio_runtime_devices(
                "USB mic (alsa_input.usb-mic)",
                "Virtual mic (ai-virtual-cam)",
                {"USB mic (alsa_input.usb-mic)": "alsa_input.usb-mic"},
                {"Virtual mic (ai-virtual-cam)": "ai-virtual-cam"},
            )

        self.assertEqual(raw_input, "alsa_input.usb-mic")
        self.assertEqual(raw_output, "ai-virtual-cam")

    def test_resolve_and_validate_audio_runtime_devices_rejects_missing_output(self) -> None:
        with mock.patch.object(self.audio_devices.platform, "system", return_value="Linux"), mock.patch.object(
            self.audio_devices,
            "_pactl_short_entries",
            side_effect=lambda kind: [
                ("1", "alsa_input.usb-mic", "module"),
            ]
            if kind == "source"
            else [
                ("2", "alsa_output.real-speaker", "module"),
            ],
        ):
            with self.assertRaisesRegex(ValueError, "Pulse runtime"):
                self.audio_devices._resolve_and_validate_audio_runtime_devices(
                    "alsa_input.usb-mic",
                    "ai-virtual-cam",
                )


    def test_capture_window_geometry_uses_window_manager_geometry(self) -> None:
        root = types.SimpleNamespace(
            update_idletasks=lambda: None,
            geometry=lambda: "900x700+120+80",
            winfo_geometry=lambda: "900x700+120+117",
            winfo_vrootwidth=lambda: 1920,
            winfo_vrootheight=lambda: 1080,
            winfo_screenwidth=lambda: 1920,
            winfo_screenheight=lambda: 1080,
        )
        gui = self.module.ConfigGui.__new__(self.module.ConfigGui)
        gui.root = root
        gui._window_geometry_meta_cache = {}

        self.module.ConfigGui._capture_all_window_geometry_meta(gui)

        self.assertEqual(gui._window_geometry_meta_cache["windowGeometry"], "900x700+120+80")



    def test_start_serve_write_path_preserves_window_geometry_meta(self) -> None:
        root = types.SimpleNamespace(
            update_idletasks=lambda: None,
            geometry=lambda: "900x700+120+80",
            winfo_geometry=lambda: "900x700+120+117",
            winfo_vrootwidth=lambda: 1920,
            winfo_vrootheight=lambda: 1080,
            winfo_screenwidth=lambda: 1920,
            winfo_screenheight=lambda: 1080,
        )
        gui = self.module.ConfigGui.__new__(self.module.ConfigGui)
        gui.root = root
        gui.output_path = "~/.avc/setting.json"
        gui._preview_active = False
        gui._lang = "ko"
        gui._language_var = types.SimpleNamespace(get=lambda: "ko")
        gui._window_geometry_meta_cache = {}
        gui._read_geometry_meta = lambda: {}
        gui._is_serve_running = lambda: False
        gui._set_serve_status = lambda *args, **kwargs: None
        gui._show_error = lambda *args, **kwargs: None
        gui._tr = lambda key, default: default
        gui._build_config = lambda: {}
        gui._build_serve_command = lambda config_path: (_ for _ in ()).throw(RuntimeError("stop after write"))
        written = {}

        with mock.patch.object(self.module, "write_config", side_effect=lambda path, config: written.update(config)):
            self.module.ConfigGui._start_serve(gui)

        self.assertEqual(written["meta"]["language"], "ko")
        self.assertEqual(written["meta"]["windowGeometry"], "900x700+120+80")
        self.assertIn("whisperWindowGeometry", written["meta"])

    def test_apply_persistent_meta_adds_language_and_geometry_for_all_write_paths(self) -> None:
        root = types.SimpleNamespace(
            update_idletasks=lambda: None,
            geometry=lambda: "900x700+120+80",
            winfo_geometry=lambda: "900x700+120+117",
            winfo_vrootwidth=lambda: 1920,
            winfo_vrootheight=lambda: 1080,
            winfo_screenwidth=lambda: 1920,
            winfo_screenheight=lambda: 1080,
        )
        gui = self.module.ConfigGui.__new__(self.module.ConfigGui)
        gui.root = root
        gui._lang = "ko"
        gui._language_var = types.SimpleNamespace(get=lambda: "ko")
        gui._window_geometry_meta_cache = {}
        gui._read_geometry_meta = lambda: {}
        config = {}

        self.module.ConfigGui._apply_persistent_meta(gui, config)

        self.assertEqual(config["meta"]["language"], "ko")
        self.assertEqual(config["meta"]["windowGeometry"], "900x700+120+80")
        for key in self.module.DEFAULT_WINDOW_GEOMETRY_META:
            self.assertIn(key, config["meta"])

    def test_apply_window_geometry_meta_preserves_existing_meta(self) -> None:
        root = types.SimpleNamespace(
            update_idletasks=lambda: None,
            winfo_geometry=lambda: "900x700+120+80",
        )
        gui = self.module.ConfigGui.__new__(self.module.ConfigGui)
        gui.root = root
        gui._window_geometry_meta_cache = {"whisperWindowGeometry": "780x420+50+119"}
        gui._read_geometry_meta = lambda: {"whisperTranslationWindowGeometry": "780x420+2479+1078"}
        config = {"meta": {"language": "ko"}}

        self.module.ConfigGui._apply_window_geometry_meta(gui, config)

        self.assertEqual(config["meta"]["language"], "ko")
        self.assertEqual(config["meta"]["windowGeometry"], "900x700+120+80")
        self.assertEqual(config["meta"]["whisperWindowGeometry"], "780x420+50+119")
        self.assertEqual(config["meta"]["whisperTranslationWindowGeometry"], "780x420+2479+1078")
        for key in self.module.DEFAULT_WINDOW_GEOMETRY_META:
            self.assertIn(key, config["meta"])


    def test_restore_window_geometry_keeps_startup_position_when_saved_value_missing(self) -> None:
        applied = []
        root = types.SimpleNamespace(
            winfo_vrootwidth=lambda: 1920,
            winfo_vrootheight=lambda: 1080,
            winfo_screenwidth=lambda: 1920,
            winfo_screenheight=lambda: 1080,
            geometry=lambda value: applied.append(value),
        )
        gui = self.module.ConfigGui.__new__(self.module.ConfigGui)
        gui.root = root
        gui._window_geometry_meta_cache = {}

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.module.ConfigGui._restore_window_geometry(gui, {})

        self.assertEqual(applied, [])
        self.assertIn("keeping startup geometry", stdout.getvalue())
        self.assertNotIn("windowGeometry", gui._window_geometry_meta_cache)

    def test_apply_window_geometry_meta_fills_defaults_when_main_geometry_capture_fails(self) -> None:
        root = types.SimpleNamespace(
            update_idletasks=lambda: None,
            winfo_geometry=lambda: "invalid",
            winfo_vrootwidth=lambda: 1920,
            winfo_vrootheight=lambda: 1080,
            winfo_screenwidth=lambda: 1920,
            winfo_screenheight=lambda: 1080,
        )
        gui = self.module.ConfigGui.__new__(self.module.ConfigGui)
        gui.root = root
        gui._window_geometry_meta_cache = {}
        gui._read_geometry_meta = lambda: {}
        config = {"meta": {"language": "ko"}}

        self.module.ConfigGui._apply_window_geometry_meta(gui, config)

        for key, value in self.module.DEFAULT_WINDOW_GEOMETRY_META.items():
            self.assertEqual(config["meta"][key], value)

    def test_external_window_geometry_log_updates_memory_cache(self) -> None:
        gui = self.module.ConfigGui.__new__(self.module.ConfigGui)
        gui._window_geometry_meta_cache = {}

        self.module.ConfigGui._remember_external_window_geometry_from_log(
            gui,
            "[2026-06-12] [avc] whisper status: window geometry cached: key=whisperWindowGeometry geometry=780x420+50+119",
        )

        self.assertEqual(gui._window_geometry_meta_cache["whisperWindowGeometry"], "780x420+50+119")

    def test_parse_window_geometry_cache_log_rejects_invalid_geometry(self) -> None:
        self.assertIsNone(
            self.module._parse_window_geometry_cache_log(
                "[avc] whisper status: window geometry cached: key=whisperWindowGeometry geometry=invalid"
            )
        )

    def test_restore_window_geometry_uses_saved_meta_value(self) -> None:
        applied = []
        root = types.SimpleNamespace(
            winfo_screenwidth=lambda: 1920,
            winfo_screenheight=lambda: 1080,
            geometry=lambda value: applied.append(value),
        )
        gui = self.module.ConfigGui.__new__(self.module.ConfigGui)
        gui.root = root

        self.module.ConfigGui._restore_window_geometry(gui, {"windowGeometry": "900x700+120+80"})

        self.assertEqual(applied, ["900x700+120+80"])

    def test_sanitize_window_geometry_accepts_visible_geometry(self) -> None:
        geometry = self.module._sanitize_window_geometry("900x700+120+80", 1920, 1080)

        self.assertEqual(geometry, "900x700+120+80")

    def test_sanitize_window_geometry_rejects_too_small_geometry(self) -> None:
        geometry = self.module._sanitize_window_geometry("320x240+120+80", 1920, 1080)

        self.assertIsNone(geometry)

    def test_sanitize_window_geometry_rejects_offscreen_geometry(self) -> None:
        geometry = self.module._sanitize_window_geometry("900x700+3000+80", 1920, 1080)

        self.assertIsNone(geometry)

    def test_window_restore_extent_allows_secondary_monitor_coordinates(self) -> None:
        root = types.SimpleNamespace(
            winfo_screenwidth=lambda: 1920,
            winfo_screenheight=lambda: 1080,
        )

        width, height = self.module._window_restore_extent(root)

        self.assertEqual((width, height), (3840, 2160))
        self.assertEqual(
            self.module._sanitize_window_geometry("900x700+2912+627", width, height),
            "900x700+2912+627",
        )


if __name__ == "__main__":
    unittest.main()
