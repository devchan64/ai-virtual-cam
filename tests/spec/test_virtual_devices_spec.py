import json
import os
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AVC = REPO_ROOT / "bin" / "avc"

TEST_VIDEO_DEVICE = "/dev/video42"
TEST_CAMERA_LABEL = "ai-virtual-cam-test"
TEST_AUDIO_SINK = "ai-virtual-cam-test"
TEST_AUDIO_SOURCE = "ai-virtual-cam-test-mic"


def _run_avc_device(args: list[str], extra_env: dict[str, str] | None = None) -> dict:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(
        [str(AVC), "device", *args],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"command failed: {' '.join(args)}\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )
    line = (proc.stdout or "").strip().splitlines()[-1]
    return json.loads(line)


class VirtualDevicesSpecIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if os.uname().sysname != "Linux":
            raise unittest.SkipTest("Linux only")
        if not AVC.exists():
            raise unittest.SkipTest("avc entrypoint not found")
        if os.environ.get("AVC_RUN_DEVICE_INTEGRATION_TEST", "0") != "1":
            raise unittest.SkipTest(
                "Set AVC_RUN_DEVICE_INTEGRATION_TEST=1 to run real virtual-device integration tests"
            )

    def tearDown(self) -> None:
        # Best-effort cleanup for isolation from user environment.
        try:
            _run_avc_device(
                ["audio", "delete"],
                {
                    "AVC_AUDIO_SINK_NAME": TEST_AUDIO_SINK,
                    "AVC_AUDIO_SINK_DESC": TEST_AUDIO_SINK,
                    "AVC_AUDIO_SOURCE_NAME": TEST_AUDIO_SOURCE,
                    "AVC_AUDIO_SOURCE_DESC": TEST_AUDIO_SOURCE,
                },
            )
        except Exception:
            pass
        try:
            _run_avc_device(
                ["camera", "delete"],
                {
                    "AVC_OUTPUT_DEVICE": TEST_VIDEO_DEVICE,
                    "AVC_CAMERA_LABEL": TEST_CAMERA_LABEL,
                },
            )
        except Exception:
            pass

    def test_virtual_audio_create_status_delete_contract(self) -> None:
        env = {
            "AVC_AUDIO_SINK_NAME": TEST_AUDIO_SINK,
            "AVC_AUDIO_SINK_DESC": TEST_AUDIO_SINK,
            "AVC_AUDIO_SOURCE_NAME": TEST_AUDIO_SOURCE,
            "AVC_AUDIO_SOURCE_DESC": TEST_AUDIO_SOURCE,
        }

        created = _run_avc_device(["audio", "create"], env)
        self.assertTrue(created.get("ok"))
        self.assertIn(TEST_AUDIO_SINK, created.get("action", ""))
        self.assertIn(TEST_AUDIO_SOURCE, created.get("action", ""))

        status = _run_avc_device(["audio", "status"], env)
        self.assertTrue(status.get("sinkExists"))
        self.assertTrue(status.get("sourceExists"))
        self.assertEqual(status.get("sinkName"), TEST_AUDIO_SINK)
        self.assertEqual(status.get("sourceName"), TEST_AUDIO_SOURCE)
        sinks = subprocess.run(
            ["pactl", "list", "short", "sinks"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(sinks.returncode, 0, msg=sinks.stderr)
        self.assertIn(TEST_AUDIO_SINK, sinks.stdout)
        sources = subprocess.run(
            ["pactl", "list", "short", "sources"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(sources.returncode, 0, msg=sources.stderr)
        self.assertIn(TEST_AUDIO_SOURCE, sources.stdout)

        deleted = _run_avc_device(["audio", "delete"], env)
        self.assertTrue(deleted.get("ok"))
        self.assertIn(TEST_AUDIO_SINK, deleted.get("action", ""))
        self.assertIn(TEST_AUDIO_SOURCE, deleted.get("action", ""))

        status_after = _run_avc_device(["audio", "status"], env)
        self.assertFalse(status_after.get("sinkExists"))
        self.assertFalse(status_after.get("sourceExists"))

    def test_virtual_camera_create_status_delete_contract(self) -> None:
        env = {
            "AVC_OUTPUT_DEVICE": TEST_VIDEO_DEVICE,
            "AVC_CAMERA_LABEL": TEST_CAMERA_LABEL,
        }

        created = _run_avc_device(["camera", "create", "--exclusive-caps", "1"], env)
        self.assertTrue(created.get("ok"))
        self.assertIn(TEST_VIDEO_DEVICE, created.get("action", ""))

        status = _run_avc_device(["camera", "status"], env)
        # moduleLoaded can be environment-dependent (lsmod visibility/race);
        # device existence is the stable contract for camera creation.
        self.assertTrue(status.get("deviceExists"))
        self.assertEqual(status.get("devicePath"), TEST_VIDEO_DEVICE)
        self.assertTrue(Path(TEST_VIDEO_DEVICE).exists())
        probe = subprocess.run(
            ["v4l2-ctl", "-D", "-d", TEST_VIDEO_DEVICE],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            probe.returncode,
            0,
            msg=f"v4l2 probe failed: stdout={probe.stdout}\nstderr={probe.stderr}",
        )
        self.assertIn(TEST_CAMERA_LABEL, probe.stdout)
        self.assertIn("Video Output", probe.stdout + probe.stderr)

        deleted = _run_avc_device(["camera", "delete"], env)
        self.assertTrue(deleted.get("ok"))

        status_after = _run_avc_device(["camera", "status"], env)
        self.assertFalse(status_after.get("deviceExists"))


if __name__ == "__main__":
    unittest.main()
