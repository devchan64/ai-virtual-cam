import contextlib
import importlib
import io
import importlib.util
import json
import sys
import tempfile
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


class _DummyVar:
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value


class _DummyWidget:
    def __init__(self):
        self.values = ()
        self.states = []

    def __setitem__(self, key, value):
        if key != "values":
            raise KeyError(key)
        self.values = tuple(value)

    def state(self, states):
        self.states.extend(states)


class _DummyFrame:
    def __init__(self):
        self.visible = True

    def grid(self):
        self.visible = True

    def grid_remove(self):
        self.visible = False




class _GridChild:
    def __init__(self, row):
        self.row = row
        self.visible = True

    def grid_info(self):
        return {"row": self.row} if self.visible else {}

    def grid_remove(self):
        self.visible = False

    def grid(self):
        self.visible = True


class _GridParent:
    def __init__(self, children):
        self._children = children

    def winfo_children(self):
        return list(self._children)


class _DummyTree:
    def __init__(self):
        self.rows = []

    def get_children(self):
        return list(range(len(self.rows)))

    def delete(self, item):
        self.rows.pop(item)

    def insert(self, parent, index, values):
        self.rows.append(tuple(values))

    def item(self, item, option=None, **kwargs):
        if "values" in kwargs:
            self.rows[item] = tuple(kwargs["values"])
        if option == "values":
            return self.rows[item]
        return {"values": self.rows[item]}




class ConfigGuiAudioValidationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_config_gui_module()
        cls.audio_devices = importlib.import_module("scripts.config.audio_devices")


    def test_dictation_ai_tab_i18n_keys_exist_for_korean_and_english(self) -> None:
        source = (REPO_ROOT / "scripts" / "config" / "dictation_ai_tab.py").read_text(encoding="utf-8")
        import re
        keys = set(re.findall(r'"((?:label|hint|button)\.dictation_ai[^"]+)"', source))
        self.assertGreater(len(keys), 20)

        for lang in ("ko", "en"):
            pack = self.module._read_flat_yaml(self.module.LANG_PACK_DIR / f"config-gui.{lang}.yaml")
            missing = sorted(key for key in keys if key not in pack)
            self.assertEqual(missing, [], f"missing dictation AI i18n keys for {lang}")



    def test_grid_rows_restores_rows_after_grid_remove(self) -> None:
        first = _GridChild(1)
        second = _GridChild(2)
        parent = _GridParent([first, second])
        gui = self.module.ConfigGui.__new__(self.module.ConfigGui)
        gui._grid_row_cache = {}

        self.module.ConfigGui._grid_rows(gui, parent, [2], False)
        self.assertTrue(first.visible)
        self.assertFalse(second.visible)

        self.module.ConfigGui._grid_rows(gui, parent, [2], True)
        self.assertTrue(second.visible)

    def test_register_hidden_dictation_ai_vars_includes_grouped_translation_settings(self) -> None:
        gui = self.module.ConfigGui.__new__(self.module.ConfigGui)
        gui.vars = {}
        defaults = {
            "dictation_ai_sentence_boundary_device": "cuda",
            "dictation_ai_sentence_boundary_compute_type": "float16",
        }
        for lang in ("en", "ko", "zh"):
            defaults.update(
                {
                    f"dictation_ai_translation_backend_{lang}": "mock",
                    f"dictation_ai_translation_model_{lang}": "",
                    f"dictation_ai_translation_device_{lang}": "cuda",
                    f"dictation_ai_translation_compute_type_{lang}": "float16",
                    f"dictation_ai_translation_beam_size_{lang}": "1",
                    f"dictation_ai_translation_max_new_tokens_{lang}": "128",
                }
            )

        with (
            mock.patch.object(self.module.ConfigGui, "_build_video_defaults", return_value=defaults),
            mock.patch.object(self.module.tk, "StringVar", side_effect=lambda value="": _DummyVar(value)),
        ):
            self.module.ConfigGui._register_hidden_dictation_ai_vars(gui)

        self.assertIn("dictation_ai_translation_backend_en", gui.vars)
        self.assertIn("dictation_ai_translation_backend_ko", gui.vars)
        self.assertIn("dictation_ai_translation_backend_zh", gui.vars)
        self.assertEqual(gui.vars["dictation_ai_translation_backend_en"].get(), "mock")

    def test_dictation_ai_platform_policy_forces_off_and_disables_enable_toggles_on_macos(self) -> None:
        gui = self.module.ConfigGui.__new__(self.module.ConfigGui)
        gui._dictation_ai_supported = False
        gui.vars = {
            "dictation_ai_enabled": _DummyVar(True),
            "dictation_ai_translation_enabled": _DummyVar(True),
            "dictation_ai_show_stt_status_window": _DummyVar(True),
        }
        gui._set_var = lambda key, value: gui.vars[key].set(bool(value))
        gui._widgets = {
            "dictation_ai_enabled": _DummyWidget(),
            "dictation_ai_input_device": _DummyWidget(),
            "dictation_ai_translation_enabled": _DummyWidget(),
            "dictation_ai_show_stt_status_window": _DummyWidget(),
            "audio_enabled": _DummyWidget(),
        }
        gui._slider_entries = {"dictation_ai_step_seconds": _DummyWidget()}

        self.module.ConfigGui._apply_dictation_ai_platform_policy(gui)

        self.assertFalse(gui.vars["dictation_ai_enabled"].get())
        self.assertFalse(gui.vars["dictation_ai_translation_enabled"].get())
        self.assertFalse(gui.vars["dictation_ai_show_stt_status_window"].get())
        self.assertIn("disabled", gui._widgets["dictation_ai_enabled"].states)
        self.assertIn("disabled", gui._widgets["dictation_ai_translation_enabled"].states)
        self.assertIn("disabled", gui._widgets["dictation_ai_show_stt_status_window"].states)
        self.assertEqual(gui._widgets["dictation_ai_input_device"].states, [])
        self.assertEqual(gui._slider_entries["dictation_ai_step_seconds"].states, [])
        self.assertEqual(gui._widgets["audio_enabled"].states, [])

    def test_camera_server_off_forces_camera_feature_toggles_off_and_disabled(self) -> None:
        gui = self.module.ConfigGui.__new__(self.module.ConfigGui)
        gui.vars = {
            "camera_server_enabled": _DummyVar(False),
            "seg_enabled": _DummyVar(True),
            "bg_enabled": _DummyVar(True),
            "crop_enabled": _DummyVar(True),
            "face_enhance_enabled": _DummyVar(True),
            "face_deidentify_enabled": _DummyVar(True),
        }
        gui._set_var = lambda key, value: gui.vars[key].set(bool(value))
        gui._widgets = {key: _DummyWidget() for key in gui.vars}

        self.module.ConfigGui._apply_camera_server_feature_policy(gui)

        for key in (
            "seg_enabled",
            "bg_enabled",
            "crop_enabled",
            "face_enhance_enabled",
            "face_deidentify_enabled",
        ):
            self.assertFalse(gui.vars[key].get(), key)
            self.assertIn("disabled", gui._widgets[key].states)

    def test_camera_server_on_enables_camera_feature_toggles_without_forcing_on(self) -> None:
        gui = self.module.ConfigGui.__new__(self.module.ConfigGui)
        gui.vars = {
            "camera_server_enabled": _DummyVar(True),
            "seg_enabled": _DummyVar(False),
            "bg_enabled": _DummyVar(False),
            "crop_enabled": _DummyVar(False),
            "face_enhance_enabled": _DummyVar(False),
            "face_deidentify_enabled": _DummyVar(False),
        }
        gui._set_var = lambda key, value: gui.vars[key].set(bool(value))
        gui._widgets = {key: _DummyWidget() for key in gui.vars}

        self.module.ConfigGui._apply_camera_server_feature_policy(gui)

        for key in (
            "seg_enabled",
            "bg_enabled",
            "crop_enabled",
            "face_enhance_enabled",
            "face_deidentify_enabled",
        ):
            self.assertFalse(gui.vars[key].get(), key)
            self.assertIn("!disabled", gui._widgets[key].states)

    def test_load_existing_config_defaults_missing_camera_feature_enabled_flags(self) -> None:
        gui = self.module.ConfigGui.__new__(self.module.ConfigGui)
        calls = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "setting.json"
            config_path.write_text(
                json.dumps(
                    {
                        "cameraServer": {},
                        "segmentation": {"backend": "mock", "selfie": {}},
                        "background": {"mode": "chroma"},
                        "crop": {},
                        "audio": {},
                        "dictationAi": {},
                    }
                ),
                encoding="utf-8",
            )
            gui.output_path = str(config_path)
            gui._language_var = _DummyVar("ko")
            gui._read_geometry_meta = mock.Mock(return_value={})
            gui._restore_window_geometry = mock.Mock()
            gui._build_video_defaults = mock.Mock(
                return_value={
                    "camera_server_enabled": True,
                    "seg_enabled": True,
                    "bg_enabled": True,
                    "crop_enabled": True,
                }
            )
            gui._set_var = mock.Mock(side_effect=lambda key, value: calls.setdefault(key, value))
            gui._apply_seg_engine_options_to_form = mock.Mock()
            gui._apply_camera_server_feature_policy = mock.Mock()
            gui._load_dictation_ai_settings_from_config = mock.Mock()
            gui._apply_dictation_ai_platform_policy = mock.Mock()
            gui._load_audio_settings_from_config = mock.Mock()
            gui._on_input_device_changed = mock.Mock()
            gui._on_input_width_changed = mock.Mock()
            gui._on_output_device_changed = mock.Mock()
            gui._on_output_height_changed = mock.Mock()

            self.module.ConfigGui._load_existing_config(gui)

        self.assertTrue(calls["camera_server_enabled"])
        self.assertTrue(calls["seg_enabled"])
        self.assertTrue(calls["bg_enabled"])
        self.assertTrue(calls["crop_enabled"])

    def test_reset_settings_json_cancels_without_writing_config(self) -> None:
        gui = self.module.ConfigGui.__new__(self.module.ConfigGui)
        gui.output_path = "/tmp/setting.json"
        gui._tr = lambda key, default: default
        gui._reset_all_form_settings = mock.Mock()
        gui._build_config = mock.Mock()
        gui._apply_persistent_meta = mock.Mock()
        gui._reset_window_geometry_file = mock.Mock()
        gui._show_error = mock.Mock()

        with (
            mock.patch.object(self.module.messagebox, "askyesno", return_value=False),
            mock.patch.object(self.module, "write_config") as write_config_mock,
        ):
            self.module.ConfigGui._reset_settings_json(gui)

        gui._reset_all_form_settings.assert_not_called()
        gui._build_config.assert_not_called()
        gui._apply_persistent_meta.assert_not_called()
        gui._reset_window_geometry_file.assert_not_called()
        write_config_mock.assert_not_called()
        gui._show_error.assert_not_called()

    def test_reset_settings_json_restores_defaults_and_writes_config(self) -> None:
        gui = self.module.ConfigGui.__new__(self.module.ConfigGui)
        gui.output_path = "/tmp/setting.json"
        gui._tr = lambda key, default: default
        gui._reset_all_form_settings = mock.Mock()
        gui._build_config = mock.Mock(return_value={"cameraServer": {"enabled": True}})
        gui._apply_persistent_meta = mock.Mock()
        gui._reset_window_geometry_file = mock.Mock()
        gui._show_error = mock.Mock()

        with (
            mock.patch.object(self.module.messagebox, "askyesno", return_value=True),
            mock.patch.object(self.module.messagebox, "showinfo") as showinfo,
            mock.patch.object(self.module, "write_config") as write_config_mock,
        ):
            self.module.ConfigGui._reset_settings_json(gui)

        gui._reset_all_form_settings.assert_called_once_with()
        gui._build_config.assert_called_once_with(validate_audio=False)
        gui._apply_persistent_meta.assert_called_once_with({"cameraServer": {"enabled": True}})
        write_config_mock.assert_called_once_with("/tmp/setting.json", {"cameraServer": {"enabled": True}})
        gui._reset_window_geometry_file.assert_called_once_with()
        showinfo.assert_called_once()
        gui._show_error.assert_not_called()

    def test_reset_window_geometry_file_writes_default_geometry_contract(self) -> None:
        gui = self.module.ConfigGui.__new__(self.module.ConfigGui)
        root = types.SimpleNamespace(after_cancel=mock.Mock())
        gui.root = root
        gui._window_geometry_save_after_id = "after-1"
        gui._window_geometry_meta_cache = {"windowGeometry": "999x999+1+1"}

        with tempfile.TemporaryDirectory() as tmpdir:
            gui.output_path = str(Path(tmpdir) / "setting.json")
            self.module.ConfigGui._reset_window_geometry_file(gui)
            geometry = json.loads((Path(tmpdir) / self.module.WINDOW_GEOMETRY_FILE_NAME).read_text(encoding="utf-8"))

        root.after_cancel.assert_called_once_with("after-1")
        self.assertIsNone(gui._window_geometry_save_after_id)
        self.assertEqual(geometry, self.module.DEFAULT_WINDOW_GEOMETRY_META)
        self.assertEqual(gui._window_geometry_meta_cache, self.module.DEFAULT_WINDOW_GEOMETRY_META)

    def test_dictation_ai_stt_gui_shows_only_selected_language_options(self) -> None:
        gui = self.module.ConfigGui.__new__(self.module.ConfigGui)
        gui.vars = {
            "dictation_ai_language": _DummyVar("한국어 (ko)"),
            "dictation_ai_stt_backend_en": _DummyVar("faster-whisper"),
            "dictation_ai_stt_model_en": _DummyVar("large-v3"),
            "dictation_ai_stt_backend_ko": _DummyVar("faster-whisper"),
            "dictation_ai_stt_model_ko": _DummyVar("large-v3"),
            "dictation_ai_stt_backend_zh": _DummyVar("qwen3-asr-transformers"),
            "dictation_ai_stt_model_zh": _DummyVar("qwen3-asr-0.6b"),
            "dictation_ai_sentence_boundary_backend": _DummyVar("sat"),
            "dictation_ai_sentence_boundary_model": _DummyVar("sat-3l-sm"),
        }
        gui._widgets = {key: _DummyWidget() for key in gui.vars if key != "dictation_ai_language"}
        gui._dictation_ai_tab = object()
        gui._dictation_ai_stt_frame = _DummyFrame()
        gui._dictation_ai_global_stt_rows = [10, 11]
        gui._dictation_ai_stt_language_rows = {"en": [1, 2], "ko": [3, 4], "zh": [5, 6]}
        gui._dictation_ai_stt_boundary_rows = [20, 21, 22]
        gui._dictation_ai_selected_stt_language = None
        gui._dictation_ai_stt_language_runtime_state = {}
        gui._dictation_ai_runtime_by_language = {}
        gui._dictation_ai_backend_option_rows = {
            "compute_type": 30,
            "beam_size": 31,
            "max_new_tokens": 32,
            "temperature": 33,
        }
        gui._dictation_ai_backend_specific_rows = list(gui._dictation_ai_backend_option_rows.values())
        gui._schedule_update_scrollbar_state = lambda: None
        grid_calls = []
        gui._grid_rows = lambda parent, rows, visible: grid_calls.append((parent, tuple(rows), visible))

        self.module.ConfigGui._sync_dictation_ai_runtime_options(gui)

        stt_visibility = {
            rows: visible for parent, rows, visible in grid_calls if parent is gui._dictation_ai_stt_frame
        }
        self.assertFalse(stt_visibility[(1, 2)])
        self.assertTrue(stt_visibility[(3, 4)])
        self.assertFalse(stt_visibility[(5, 6)])
        self.assertEqual(gui._widgets["dictation_ai_stt_backend_ko"].values, ("faster-whisper", "mock"))
        backend_option_visibility = {
            rows: visible for parent, rows, visible in grid_calls if parent is gui._dictation_ai_tab
        }
        self.assertTrue(backend_option_visibility[(32,)])
        self.assertTrue(backend_option_visibility[(33,)])

        grid_calls.clear()
        gui.vars["dictation_ai_language"].set("中文 (zh)")
        self.module.ConfigGui._sync_dictation_ai_runtime_options(gui)

        stt_visibility = {
            rows: visible for parent, rows, visible in grid_calls if parent is gui._dictation_ai_stt_frame
        }
        self.assertFalse(stt_visibility[(1, 2)])
        self.assertFalse(stt_visibility[(3, 4)])
        self.assertTrue(stt_visibility[(5, 6)])
        self.assertEqual(
            gui._widgets["dictation_ai_stt_backend_zh"].values,
            ("faster-whisper", "qwen3-asr-transformers", "mock"),
        )
        self.assertEqual(gui._widgets["dictation_ai_stt_model_zh"].values, ("qwen3-asr-0.6b", "qwen3-asr-1.7b"))
        backend_option_visibility = {
            rows: visible for parent, rows, visible in grid_calls if parent is gui._dictation_ai_tab
        }
        self.assertTrue(backend_option_visibility[(32,)])
        self.assertFalse(backend_option_visibility[(33,)])

        grid_calls.clear()
        gui.vars["dictation_ai_stt_backend_zh"].set("faster-whisper")
        self.module.ConfigGui._sync_dictation_ai_runtime_options(gui)
        backend_option_visibility = {
            rows: visible for parent, rows, visible in grid_calls if parent is gui._dictation_ai_tab
        }
        self.assertTrue(backend_option_visibility[(32,)])
        self.assertTrue(backend_option_visibility[(33,)])
        self.assertEqual(gui.vars["dictation_ai_stt_backend_zh"].get(), "faster-whisper")
        self.assertEqual(gui._widgets["dictation_ai_stt_model_zh"].values, ("large-v3", "medium", "small", "base", "tiny"))

    def test_dictation_ai_translation_gui_groups_settings_by_target_language(self) -> None:
        gui = self.module.ConfigGui.__new__(self.module.ConfigGui)
        gui.vars = {
            "dictation_ai_language": _DummyVar("中文 (zh)"),
            "dictation_ai_translation_target_language": _DummyVar("한국어 (ko)"),
            "dictation_ai_translation_backend": _DummyVar("nllb-transformers"),
            "dictation_ai_translation_model": _DummyVar("facebook/nllb-200-distilled-600M"),
            "dictation_ai_translation_device": _DummyVar("cuda"),
            "dictation_ai_translation_compute_type": _DummyVar("float16"),
            "dictation_ai_translation_beam_size": _DummyVar("2"),
            "dictation_ai_translation_max_new_tokens": _DummyVar("128"),
            "dictation_ai_translation_backend_en": _DummyVar("whisper"),
            "dictation_ai_translation_model_en": _DummyVar(""),
            "dictation_ai_translation_device_en": _DummyVar("cuda"),
            "dictation_ai_translation_compute_type_en": _DummyVar("float16"),
            "dictation_ai_translation_beam_size_en": _DummyVar("1"),
            "dictation_ai_translation_max_new_tokens_en": _DummyVar("128"),
            "dictation_ai_translation_backend_ko": _DummyVar("nllb-transformers"),
            "dictation_ai_translation_model_ko": _DummyVar("facebook/nllb-200-distilled-600M"),
            "dictation_ai_translation_device_ko": _DummyVar("cuda"),
            "dictation_ai_translation_compute_type_ko": _DummyVar("float16"),
            "dictation_ai_translation_beam_size_ko": _DummyVar("2"),
            "dictation_ai_translation_max_new_tokens_ko": _DummyVar("128"),
            "dictation_ai_translation_backend_zh": _DummyVar("m2m100-transformers"),
            "dictation_ai_translation_model_zh": _DummyVar("facebook/m2m100_1.2B"),
            "dictation_ai_translation_device_zh": _DummyVar("cuda"),
            "dictation_ai_translation_compute_type_zh": _DummyVar("float16"),
            "dictation_ai_translation_beam_size_zh": _DummyVar("1"),
            "dictation_ai_translation_max_new_tokens_zh": _DummyVar("96"),
        }
        gui._widgets = {
            "dictation_ai_translation_backend": _DummyWidget(),
            "dictation_ai_translation_target_language": _DummyWidget(),
            "dictation_ai_translation_model": _DummyWidget(),
        }
        gui._dictation_ai_translation_backend_frames = {
            "whisper": _DummyFrame(),
            "nllb-transformers": _DummyFrame(),
            "m2m100-transformers": _DummyFrame(),
            "mock": _DummyFrame(),
        }
        gui._schedule_update_scrollbar_state = lambda: None

        self.module.ConfigGui._sync_dictation_ai_translation_backend_options(gui)

        self.assertNotIn("whisper", gui._widgets["dictation_ai_translation_backend"].values)
        self.assertEqual(gui.vars["dictation_ai_translation_backend"].get(), "nllb-transformers")

        gui.vars["dictation_ai_translation_model"].set("facebook/nllb-200-1.3B")
        gui.vars["dictation_ai_translation_beam_size"].set("4")
        gui.vars["dictation_ai_translation_target_language"].set("中文 (zh)")
        self.module.ConfigGui._on_dictation_ai_translation_target_changed(gui)

        self.assertEqual(gui.vars["dictation_ai_translation_model_ko"].get(), "facebook/nllb-200-1.3B")
        self.assertEqual(gui.vars["dictation_ai_translation_beam_size_ko"].get(), "4")
        self.assertEqual(gui.vars["dictation_ai_translation_backend"].get(), "m2m100-transformers")
        self.assertEqual(gui.vars["dictation_ai_translation_model"].get(), "facebook/m2m100_1.2B")
        self.assertEqual(gui.vars["dictation_ai_translation_max_new_tokens"].get(), "96")

        gui.vars["dictation_ai_translation_target_language"].set("English (en)")
        self.module.ConfigGui._on_dictation_ai_translation_target_changed(gui)

        self.assertIn("whisper", gui._widgets["dictation_ai_translation_backend"].values)
        self.assertEqual(gui.vars["dictation_ai_translation_backend"].get(), "whisper")
        self.assertEqual(gui.vars["dictation_ai_translation_target_language"].get(), "English (en)")

        gui.vars["dictation_ai_translation_target_language"].set("한국어 (ko)")
        self.module.ConfigGui._on_dictation_ai_translation_target_changed(gui)

        self.assertNotIn("whisper", gui._widgets["dictation_ai_translation_backend"].values)
        self.assertEqual(gui.vars["dictation_ai_translation_target_language"].get(), "한국어 (ko)")
        self.assertEqual(gui.vars["dictation_ai_translation_backend"].get(), "nllb-transformers")
        self.assertEqual(gui.vars["dictation_ai_translation_model"].get(), "facebook/nllb-200-1.3B")

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



    def test_start_serve_write_path_saves_window_geometry_file(self) -> None:
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
        with tempfile.TemporaryDirectory() as tmpdir:
            gui.output_path = str(Path(tmpdir) / "setting.json")
            gui._preview_active = False
            gui._lang = "ko"
            gui._language_var = types.SimpleNamespace(get=lambda: "ko")
            gui._window_geometry_meta_cache = {}
            gui._is_serve_running = lambda: False
            gui._set_serve_status = lambda *args, **kwargs: None
            gui._show_error = lambda *args, **kwargs: None
            gui._tr = lambda key, default: default
            gui._build_config = lambda: {}
            gui._build_serve_command = lambda config_path: (_ for _ in ()).throw(RuntimeError("stop after write"))
            written = {}

            with mock.patch.object(self.module, "write_config", side_effect=lambda path, config: written.update(config)):
                self.module.ConfigGui._start_serve(gui)

            geometry = json.loads((Path(tmpdir) / self.module.WINDOW_GEOMETRY_FILE_NAME).read_text(encoding="utf-8"))

        self.assertEqual(written["meta"], {"language": "ko"})
        self.assertEqual(geometry["windowGeometry"], "900x700+120+80")
        self.assertIn("dictationAiWindowGeometry", geometry)

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
        with tempfile.TemporaryDirectory() as tmpdir:
            gui.output_path = str(Path(tmpdir) / "setting.json")
            gui._window_geometry_meta_cache = {}
            config = {}

            self.module.ConfigGui._apply_persistent_meta(gui, config)
            geometry = json.loads((Path(tmpdir) / self.module.WINDOW_GEOMETRY_FILE_NAME).read_text(encoding="utf-8"))

        self.assertEqual(config["meta"]["language"], "ko")
        self.assertNotIn("windowGeometry", config["meta"])
        self.assertEqual(geometry["windowGeometry"], "900x700+120+80")
        for key in self.module.DEFAULT_WINDOW_GEOMETRY_META:
            self.assertIn(key, geometry)

    def test_apply_window_geometry_meta_preserves_existing_geometry_file(self) -> None:
        root = types.SimpleNamespace(
            update_idletasks=lambda: None,
            winfo_geometry=lambda: "900x700+120+80",
        )
        gui = self.module.ConfigGui.__new__(self.module.ConfigGui)
        gui.root = root
        with tempfile.TemporaryDirectory() as tmpdir:
            gui.output_path = str(Path(tmpdir) / "setting.json")
            (Path(tmpdir) / self.module.WINDOW_GEOMETRY_FILE_NAME).write_text(
                json.dumps({"dictationAiTranslationWindowGeometry": "780x420+2479+1078"}),
                encoding="utf-8",
            )
            gui._window_geometry_meta_cache = {"dictationAiWindowGeometry": "780x420+50+119"}
            config = {"meta": {"language": "ko", "windowGeometry": "legacy"}}

            self.module.ConfigGui._apply_window_geometry_meta(gui, config)
            geometry = json.loads((Path(tmpdir) / self.module.WINDOW_GEOMETRY_FILE_NAME).read_text(encoding="utf-8"))

        self.assertEqual(config["meta"]["language"], "ko")
        self.assertNotIn("windowGeometry", config["meta"])
        self.assertEqual(geometry["windowGeometry"], "900x700+120+80")
        self.assertEqual(geometry["dictationAiWindowGeometry"], "780x420+50+119")
        self.assertEqual(geometry["dictationAiTranslationWindowGeometry"], "780x420+2479+1078")
        for key in self.module.DEFAULT_WINDOW_GEOMETRY_META:
            self.assertIn(key, geometry)


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
        with tempfile.TemporaryDirectory() as tmpdir:
            gui.output_path = str(Path(tmpdir) / "setting.json")
            gui._window_geometry_meta_cache = {}
            config = {"meta": {"language": "ko"}}

            self.module.ConfigGui._apply_window_geometry_meta(gui, config)
            geometry = json.loads((Path(tmpdir) / self.module.WINDOW_GEOMETRY_FILE_NAME).read_text(encoding="utf-8"))

        self.assertEqual(config["meta"], {"language": "ko"})
        for key, value in self.module.DEFAULT_WINDOW_GEOMETRY_META.items():
            self.assertEqual(geometry[key], value)

    def test_external_window_geometry_log_updates_memory_cache(self) -> None:
        gui = self.module.ConfigGui.__new__(self.module.ConfigGui)
        gui._window_geometry_meta_cache = {}

        self.module.ConfigGui._remember_external_window_geometry_from_log(
            gui,
            "[2026-06-12] [avc] Dictation AI status: window geometry cached: key=dictationAiWindowGeometry geometry=780x420+50+119",
        )

        self.assertEqual(gui._window_geometry_meta_cache["dictationAiWindowGeometry"], "780x420+50+119")

    def test_parse_window_geometry_cache_log_rejects_invalid_geometry(self) -> None:
        self.assertIsNone(
            self.module._parse_window_geometry_cache_log(
                "[avc] Dictation AI status: window geometry cached: key=dictationAiWindowGeometry geometry=invalid"
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


    def test_default_window_geometry_meta_contains_dictation_ai_model_download_window_geometry(self) -> None:
        self.assertIn("dictationAiModelDownloadWindowGeometry", self.module.DEFAULT_WINDOW_GEOMETRY_META)
        self.assertIn("dictationAiInputMeterWindowGeometry", self.module.DEFAULT_WINDOW_GEOMETRY_META)

    def test_capture_all_window_geometry_meta_remembers_dictation_ai_model_download_window(self) -> None:
        root = types.SimpleNamespace(
            update_idletasks=lambda: None,
            geometry=lambda: "900x700+120+80",
            winfo_vrootwidth=lambda: 1920,
            winfo_vrootheight=lambda: 1080,
            winfo_screenwidth=lambda: 1920,
            winfo_screenheight=lambda: 1080,
        )
        gui = self.module.ConfigGui.__new__(self.module.ConfigGui)
        gui.root = root
        gui._window_geometry_meta_cache = {}
        download_window = object()
        meter_window = object()
        gui._managed_window_geometry = {
            download_window: "dictationAiModelDownloadWindowGeometry",
            meter_window: "dictationAiInputMeterWindowGeometry",
        }

        with mock.patch.object(self.module.ConfigGui, "_remember_named_window_geometry") as remember:
            self.module.ConfigGui._capture_all_window_geometry_meta(gui)

        remember.assert_any_call("dictationAiModelDownloadWindowGeometry", download_window)
        remember.assert_any_call("dictationAiInputMeterWindowGeometry", meter_window)

    def test_register_managed_window_geometry_restores_and_binds_configure(self) -> None:
        window = mock.Mock()
        gui = self.module.ConfigGui.__new__(self.module.ConfigGui)
        gui._managed_window_geometry = {}
        gui._restore_named_window_geometry = mock.Mock()

        self.module.ConfigGui._register_managed_window_geometry(gui, window, "audioTuneWindowGeometry")

        gui._restore_named_window_geometry.assert_called_once_with(window, "audioTuneWindowGeometry", None)
        self.assertEqual(gui._managed_window_geometry[window], "audioTuneWindowGeometry")
        window.bind.assert_called_once_with("<Configure>", gui._on_managed_window_configure, add="+")

    def test_managed_window_configure_remembers_and_schedules_geometry_capture(self) -> None:
        window = object()
        gui = self.module.ConfigGui.__new__(self.module.ConfigGui)
        gui._managed_window_geometry = {window: "audioGateTestWindowGeometry"}
        gui._remember_named_window_geometry = mock.Mock()
        gui._schedule_save_window_geometry_meta = mock.Mock()

        event = types.SimpleNamespace(widget=window)
        self.module.ConfigGui._on_managed_window_configure(gui, event)

        gui._remember_named_window_geometry.assert_called_once_with("audioGateTestWindowGeometry", window)
        gui._schedule_save_window_geometry_meta.assert_called_once_with()

    def test_flush_managed_window_geometry_remembers_and_saves(self) -> None:
        window = object()
        gui = self.module.ConfigGui.__new__(self.module.ConfigGui)
        gui._managed_window_geometry = {window: "inputMeterWindowGeometry"}
        gui._remember_named_window_geometry = mock.Mock()
        gui._save_window_geometry_file = mock.Mock()

        self.module.ConfigGui._flush_managed_window_geometry(gui, window)

        gui._remember_named_window_geometry.assert_called_once_with("inputMeterWindowGeometry", window)
        gui._save_window_geometry_file.assert_called_once_with()

    def test_dictation_ai_model_download_configure_schedules_geometry_capture(self) -> None:
        download_window = object()
        gui = self.module.ConfigGui.__new__(self.module.ConfigGui)
        gui._managed_window_geometry = {download_window: "dictationAiModelDownloadWindowGeometry"}
        gui._remember_named_window_geometry = mock.Mock()
        gui._schedule_save_window_geometry_meta = mock.Mock()

        event = types.SimpleNamespace(widget=download_window)
        self.module.ConfigGui._on_dictation_ai_model_download_configure(gui, event)

        gui._remember_named_window_geometry.assert_called_once_with("dictationAiModelDownloadWindowGeometry", download_window)
        gui._schedule_save_window_geometry_meta.assert_called_once_with()

    def test_dictation_ai_model_download_configure_ignores_other_widgets(self) -> None:
        gui = self.module.ConfigGui.__new__(self.module.ConfigGui)
        gui._managed_window_geometry = {object(): "dictationAiModelDownloadWindowGeometry"}
        gui._remember_named_window_geometry = mock.Mock()
        gui._schedule_save_window_geometry_meta = mock.Mock()

        event = types.SimpleNamespace(widget=object())
        self.module.ConfigGui._on_dictation_ai_model_download_configure(gui, event)

        gui._remember_named_window_geometry.assert_not_called()
        gui._schedule_save_window_geometry_meta.assert_not_called()

    def test_dictation_ai_model_download_command_uses_dictation_ai_block(self) -> None:
        gui = self.module.ConfigGui.__new__(self.module.ConfigGui)
        config = {
            "dictationAi": {
                "backend": "faster-whisper",
                "model": "large-v3",
                "sttBackendZh": "qwen3-asr-transformers",
                "sttModelZh": "qwen3-asr-0.6b",
                "sentenceBoundaryBackend": "sat",
                "sentenceBoundaryModel": "sat-3l-sm",
                "translationEnabled": True,
                "translationBackend": "nllb-transformers",
                "translationModel": "facebook/nllb-200-distilled-600M",
                "translationBackendKo": "nllb-transformers",
                "translationModelKo": "facebook/nllb-200-distilled-1.3B",
                "translationBackendZh": "m2m100-transformers",
                "translationModelZh": "facebook/m2m100_1.2B",
            },
            "whisper": {
                "backend": "mock",
                "model": "mock",
            },
        }

        cmd = self.module.ConfigGui._build_dictation_ai_model_download_command(gui, config)

        self.assertIn("--stt-backend", cmd)
        self.assertIn("faster-whisper", cmd)
        self.assertIn("qwen3-asr-transformers", cmd)
        self.assertIn("--boundary-backend", cmd)
        self.assertIn("sat", cmd)
        self.assertIn("--translation-backend", cmd)
        self.assertIn("nllb-transformers", cmd)
        self.assertIn("facebook/nllb-200-distilled-1.3B", cmd)
        self.assertIn("facebook/m2m100_1.2B", cmd)
        self.assertNotIn("mock", cmd)

    def test_dictation_ai_model_download_manager_populates_assets(self) -> None:
        gui = self.module.ConfigGui.__new__(self.module.ConfigGui)
        gui._dictation_ai_model_download_asset_tree = _DummyTree()
        gui._tr = lambda key, default: default
        config = {
            "dictationAi": {
                "backend": "faster-whisper",
                "model": "large-v3",
                "sttBackendZh": "qwen3-asr-transformers",
                "sttModelZh": "qwen3-asr-0.6b",
                "sentenceBoundaryBackend": "sat",
                "sentenceBoundaryModel": "sat-3l-sm",
                "translationEnabled": True,
                "translationBackend": "nllb-transformers",
                "translationModel": "facebook/nllb-200-distilled-600M",
            },
        }

        self.module.ConfigGui._populate_dictation_ai_model_download_assets(gui, config)
        rows = gui._dictation_ai_model_download_asset_tree.rows

        self.assertIn(("stt", "faster-whisper", "large-v3", "대기"), rows)
        self.assertIn(("stt", "qwen3-asr-transformers", "qwen3-asr-0.6b", "대기"), rows)
        self.assertIn(("boundary", "sat", "sat-3l-sm", "대기"), rows)
        self.assertIn(("translation", "nllb-transformers", "facebook/nllb-200-distilled-600M", "대기"), rows)

        self.module.ConfigGui._set_dictation_ai_model_download_asset_status(gui, "완료")
        self.assertTrue(all(row[3] == "완료" for row in gui._dictation_ai_model_download_asset_tree.rows))

    def test_close_dictation_ai_model_download_dialog_cancels_running_process(self) -> None:
        process = mock.Mock()
        process.poll.return_value = None
        process.send_signal = mock.Mock()
        download_window = types.SimpleNamespace(destroy=mock.Mock())

        gui = self.module.ConfigGui.__new__(self.module.ConfigGui)
        gui._dictation_ai_model_download_process = process
        gui._dictation_ai_model_download_window = download_window
        gui._dictation_ai_model_download_btn = None
        gui._dictation_ai_model_download_progress = None
        gui._dictation_ai_model_download_log_text = None
        gui._dictation_ai_model_download_on_success = None
        gui._i18n = {}
        gui._dictation_ai_model_download_cancelled = False
        gui._set_dictation_ai_model_download_status = mock.Mock()
        gui._set_serve_status = mock.Mock()
        gui._flush_managed_window_geometry = mock.Mock()
        gui._forget_managed_window_geometry = mock.Mock()

        self.module.ConfigGui._close_dictation_ai_model_download_dialog(gui, False)

        self.assertTrue(gui._dictation_ai_model_download_cancelled)
        process.send_signal.assert_called_once_with(self.module.signal.SIGINT)
        gui._flush_managed_window_geometry.assert_called_once_with(download_window)
        gui._forget_managed_window_geometry.assert_called_once_with(download_window)
        download_window.destroy.assert_called_once()
        gui._set_serve_status.assert_called_once()

    def test_dictation_ai_model_download_finished_reports_cancelled_state(self) -> None:
        gui = self.module.ConfigGui.__new__(self.module.ConfigGui)
        gui._dictation_ai_model_download_progress = types.SimpleNamespace(configure=mock.Mock())
        gui._dictation_ai_model_download_btn = types.SimpleNamespace(state=mock.Mock())
        gui._dictation_ai_model_download_cancelled = True
        gui._set_dictation_ai_model_download_status = mock.Mock()
        gui._set_serve_status = mock.Mock()
        gui._tr = lambda key, default: default

        self.module.ConfigGui._dictation_ai_model_download_finished(gui, 1, "error")

        gui._set_dictation_ai_model_download_status.assert_called_once_with("모델 다운로드가 취소되었습니다.")
        gui._set_serve_status.assert_not_called()

    def test_dictation_ai_model_download_success_rechecks_before_serve_launch(self) -> None:
        gui = self.module.ConfigGui.__new__(self.module.ConfigGui)
        config = {"dictationAi": {"enabled": True}}
        serve_cmd = ["./bin/avc", "serve"]
        gui._check_dictation_ai_models_ready_for_serve = mock.Mock(return_value=True)
        gui._launch_serve_command = mock.Mock()

        self.module.ConfigGui._continue_serve_after_dictation_ai_model_download(gui, config, serve_cmd)

        gui._check_dictation_ai_models_ready_for_serve.assert_called_once_with(config, serve_cmd)
        gui._launch_serve_command.assert_called_once_with(serve_cmd)

    def test_dictation_ai_model_download_success_blocks_serve_when_recheck_fails(self) -> None:
        gui = self.module.ConfigGui.__new__(self.module.ConfigGui)
        config = {"dictationAi": {"enabled": True}}
        serve_cmd = ["./bin/avc", "serve"]
        gui._check_dictation_ai_models_ready_for_serve = mock.Mock(return_value=False)
        gui._launch_serve_command = mock.Mock()

        self.module.ConfigGui._continue_serve_after_dictation_ai_model_download(gui, config, serve_cmd)

        gui._check_dictation_ai_models_ready_for_serve.assert_called_once_with(config, serve_cmd)
        gui._launch_serve_command.assert_not_called()

    def test_dictation_ai_input_meter_uses_dictation_ai_config_and_geometry_key(self) -> None:
        gui = self.module.ConfigGui.__new__(self.module.ConfigGui)
        gui._build_config = lambda validate_audio=False: {
            "dictationAi": {"inputDevice": "dictation-source"},
            "whisper": {"inputDevice": "legacy-source"},
        }
        gui._show_error = mock.Mock()
        gui._run_input_meter = mock.Mock()

        self.module.ConfigGui._run_dictation_ai_input_meter(gui)

        gui._run_input_meter.assert_called_once()
        kwargs = gui._run_input_meter.call_args.kwargs
        self.assertEqual(kwargs["input_device_requested"], "dictation-source")
        self.assertEqual(kwargs["geometry_key"], "dictationAiInputMeterWindowGeometry")


if __name__ == "__main__":
    unittest.main()
