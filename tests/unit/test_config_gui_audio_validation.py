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

    def test_resolve_and_validate_audio_runtime_devices_maps_display_values(self) -> None:
        with mock.patch.object(self.module.platform, "system", return_value="Linux"), mock.patch.object(
            self.module,
            "_pactl_short_entries",
            side_effect=lambda kind: [
                ("1", "alsa_input.usb-mic", "module"),
            ]
            if kind == "source"
            else [
                ("2", "ai-virtual-cam", "module"),
            ],
        ):
            raw_input, raw_output = self.module._resolve_and_validate_audio_runtime_devices(
                "USB mic (alsa_input.usb-mic)",
                "Virtual mic (ai-virtual-cam)",
                {"USB mic (alsa_input.usb-mic)": "alsa_input.usb-mic"},
                {"Virtual mic (ai-virtual-cam)": "ai-virtual-cam"},
            )

        self.assertEqual(raw_input, "alsa_input.usb-mic")
        self.assertEqual(raw_output, "ai-virtual-cam")

    def test_resolve_and_validate_audio_runtime_devices_rejects_missing_output(self) -> None:
        with mock.patch.object(self.module.platform, "system", return_value="Linux"), mock.patch.object(
            self.module,
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
                self.module._resolve_and_validate_audio_runtime_devices(
                    "alsa_input.usb-mic",
                    "ai-virtual-cam",
                )

    def test_sanitize_window_geometry_accepts_visible_geometry(self) -> None:
        geometry = self.module._sanitize_window_geometry("900x700+120+80", 1920, 1080)

        self.assertEqual(geometry, "900x700+120+80")

    def test_sanitize_window_geometry_rejects_too_small_geometry(self) -> None:
        geometry = self.module._sanitize_window_geometry("320x240+120+80", 1920, 1080)

        self.assertIsNone(geometry)

    def test_sanitize_window_geometry_rejects_offscreen_geometry(self) -> None:
        geometry = self.module._sanitize_window_geometry("900x700+3000+80", 1920, 1080)

        self.assertIsNone(geometry)


if __name__ == "__main__":
    unittest.main()
