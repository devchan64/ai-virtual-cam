import json
import os
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AVC_DEVICE = REPO_ROOT / "scripts" / "bin" / "avc-device"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


class VirtualAudioSpecTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmpdir.name)
        self.mockbin = self.tmp / "mockbin"
        self.mockbin.mkdir(parents=True, exist_ok=True)
        self.state_file = self.tmp / "pactl_state.json"
        self.state_file.write_text(
            json.dumps(
                {
                    "next_module_id": 1,
                    "sinks": [],
                    "sources": [],
                    "modules": [],
                }
            ),
            encoding="utf-8",
        )
        self._install_mocks()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _install_mocks(self) -> None:
        _write_executable(
            self.mockbin / "uname",
            "#!/usr/bin/env bash\nif [[ \"$1\" == \"-s\" ]]; then echo Linux; else /usr/bin/uname \"$@\"; fi\n",
        )

        _write_executable(
            self.mockbin / "pactl",
            textwrap.dedent(
                """\
                #!/usr/bin/env python3
                import json, os, sys

                state_path = os.environ["MOCK_PACTL_STATE"]
                with open(state_path, "r", encoding="utf-8") as f:
                    state = json.load(f)

                args = sys.argv[1:]

                def save():
                    with open(state_path, "w", encoding="utf-8") as fw:
                        json.dump(state, fw)

                if args[:3] == ["list", "short", "sinks"]:
                    for idx, sink in enumerate(state["sinks"]):
                        print(f"{idx}\\t{sink}\\tmodule-null-sink.c\\ts16le 1ch 48000Hz\\tSUSPENDED")
                    sys.exit(0)

                if args[:3] == ["list", "short", "sources"]:
                    for idx, source in enumerate(state["sources"]):
                        print(f"{idx}\\t{source}\\tmodule-remap-source.c\\ts16le 1ch 48000Hz\\tSUSPENDED")
                    sys.exit(0)

                if args[:3] == ["list", "short", "modules"]:
                    for module in state["modules"]:
                        print(f"{module['id']}\\t{module['name']}\\t{module['args']}")
                    sys.exit(0)

                if args[:2] == ["load-module", "module-null-sink"]:
                    sink_name = ""
                    sink_desc = ""
                    for arg in args[2:]:
                        if arg.startswith("sink_name="):
                            sink_name = arg.split("=", 1)[1]
                        if arg.startswith("sink_properties="):
                            sink_desc = arg.split("=", 1)[1]
                    if sink_name and sink_name not in state["sinks"]:
                        state["sinks"].append(sink_name)
                    module_id = str(state["next_module_id"])
                    state["next_module_id"] += 1
                    state["modules"].append(
                        {
                            "id": module_id,
                            "name": "module-null-sink",
                            "args": f"sink_name={sink_name} sink_properties={sink_desc}",
                        }
                    )
                    save()
                    print(module_id)
                    sys.exit(0)

                if args[:2] == ["load-module", "module-remap-source"]:
                    source_name = ""
                    master = ""
                    source_desc = ""
                    for arg in args[2:]:
                        if arg.startswith("source_name="):
                            source_name = arg.split("=", 1)[1]
                        if arg.startswith("master="):
                            master = arg.split("=", 1)[1]
                        if arg.startswith("source_properties="):
                            source_desc = arg.split("=", 1)[1]
                    if source_name and source_name not in state["sources"]:
                        state["sources"].append(source_name)
                    module_id = str(state["next_module_id"])
                    state["next_module_id"] += 1
                    state["modules"].append(
                        {
                            "id": module_id,
                            "name": "module-remap-source",
                            "args": f"source_name={source_name} master={master} source_properties={source_desc}",
                        }
                    )
                    save()
                    print(module_id)
                    sys.exit(0)

                if args[:1] == ["unload-module"]:
                    target = args[1] if len(args) > 1 else ""
                    keep = []
                    removed = None
                    for module in state["modules"]:
                        if module["id"] == target and removed is None:
                            removed = module
                        else:
                            keep.append(module)
                    state["modules"] = keep
                    if removed is not None:
                        if removed["name"] == "module-null-sink":
                            for token in removed["args"].split():
                                if token.startswith("sink_name="):
                                    sink = token.split("=", 1)[1]
                                    state["sinks"] = [x for x in state["sinks"] if x != sink]
                        if removed["name"] == "module-remap-source":
                            for token in removed["args"].split():
                                if token.startswith("source_name="):
                                    source = token.split("=", 1)[1]
                                    state["sources"] = [x for x in state["sources"] if x != source]
                    save()
                    sys.exit(0)

                print("unsupported pactl args", args, file=sys.stderr)
                sys.exit(2)
                """
            ),
        )

    def _run_device(self, *args: str) -> dict:
        env = os.environ.copy()
        env["PATH"] = f"{self.mockbin}:{env.get('PATH', '')}"
        env["MOCK_PACTL_STATE"] = str(self.state_file)
        env["AVC_AUDIO_SINK_NAME"] = "ai-virtual-cam"
        env["AVC_AUDIO_SINK_DESC"] = "ai-virtual-cam"
        env["AVC_AUDIO_SOURCE_NAME"] = "ai-virtual-cam-mic"
        env["AVC_AUDIO_SOURCE_DESC"] = "ai-virtual-cam-mic"
        proc = subprocess.run(
            [str(AVC_DEVICE), *args],
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
        self.assertEqual(
            proc.returncode,
            0,
            msg=f"command failed: {' '.join(args)}\nstdout={proc.stdout}\nstderr={proc.stderr}",
        )
        return json.loads(proc.stdout.strip().splitlines()[-1])

    def test_audio_create_status_delete_contract(self) -> None:
        created = self._run_device("audio", "create")
        self.assertTrue(created.get("ok"))
        self.assertIn("source=ai-virtual-cam-mic", created.get("action", ""))

        status = self._run_device("audio", "status")
        self.assertTrue(status.get("sinkExists"))
        self.assertTrue(status.get("sourceExists"))
        self.assertEqual(status.get("sinkName"), "ai-virtual-cam")
        self.assertEqual(status.get("sourceName"), "ai-virtual-cam-mic")

        deleted = self._run_device("audio", "delete")
        self.assertTrue(deleted.get("ok"))
        self.assertIn("source=ai-virtual-cam-mic", deleted.get("action", ""))

        status_after = self._run_device("audio", "status")
        self.assertFalse(status_after.get("sinkExists"))
        self.assertFalse(status_after.get("sourceExists"))


if __name__ == "__main__":
    unittest.main()
