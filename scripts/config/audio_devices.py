from __future__ import annotations

import os
import platform
import re
import subprocess
from pathlib import Path

try:
    import sounddevice as sd
except ModuleNotFoundError:
    sd = None


AUDIO_VIRTUAL_SINK_NAME = "ai-virtual-cam"
AUDIO_VIRTUAL_SOURCE_NAME = "ai-virtual-cam"


def _log(msg: str) -> None:
    print(f"[avc] {msg}", flush=True)


def _run_cmd(cmd: list[str], *, check: bool = False, timeout: float | None = 1.5) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=check, timeout=timeout)
    except FileNotFoundError as exc:
        raise RuntimeError(f"command not found: {cmd[0]}") from exc


def _is_container_runtime() -> bool:
    return Path("/.dockerenv").exists()


def _audio_default_output_device() -> str:
    if platform.system() != "Linux":
        return "default"
    if _is_container_runtime():
        pactl_default = _pactl_default_audio_device("sink")
        return pactl_default if pactl_default != "default" else "pulse"
    if sd is None:
        pactl_default = _pactl_default_audio_device("sink")
        return pactl_default if pactl_default != "default" else "pulse"
    try:
        sound_names: list[str] = []
        for device in sd.query_devices():
            name = str(device.get("name", ""))
            if int(device.get("max_output_channels", 0)) <= 0:
                continue
            if not name.strip():
                continue
            sound_names.append(name)
        if sound_names:
            for name in sound_names:
                lowered = name.lower()
                if "virtual" in lowered and "default" not in lowered:
                    return name
            for name in sound_names:
                lowered = name.lower()
                if "default" not in lowered and "(hw:" not in lowered and "sof-hda" not in lowered:
                    return name
            if "pulse" in sound_names:
                return "pulse"
            return sound_names[0]
    except Exception:
        pactl_default = _pactl_default_audio_device("sink")
        return pactl_default if pactl_default != "default" else "pulse"

    def _first_pulse_sink() -> str | None:
        try:
            proc = subprocess.run(
                ["pactl", "list", "short", "sinks"],
                capture_output=True,
                text=True,
                check=False,
                timeout=1.5,
            )
        except Exception:
            return None
        if proc.returncode != 0:
            return None
        for line in proc.stdout.splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue
            name = parts[1].strip()
            if not name:
                continue
            lowered = name.lower()
            if "(hw:" in lowered or "sof-hda" in lowered:
                continue
            if "ai-virtual-cam" in lowered or "virtual" in lowered:
                return name
        for line in proc.stdout.splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue
            name = parts[1].strip()
            if not name:
                continue
            lowered = name.lower()
            if "(hw:" in lowered or "sof-hda" in lowered:
                continue
            if "default" not in lowered:
                return name
        return None

    # Prefer explicitly virtual/ai-virtual-cam sink to avoid picking physical default sink.
    prefer_sink = _first_pulse_sink()
    if prefer_sink is not None:
        return prefer_sink
    pactl_default = _pactl_default_audio_device("sink")
    if pactl_default != "default" and "(hw:" not in pactl_default.lower() and "sof-hda" not in pactl_default.lower():
        return pactl_default
    return "pulse"


def _coerce_audio_output_device_for_sounddevice(device_name: str) -> str:
    def _pick_virtual_output(names: list[str]) -> str | None:
        for candidate in names:
            lowered_candidate = candidate.lower()
            if "virtual" in lowered_candidate and "default" not in lowered_candidate:
                return candidate
        return None

    if sd is None:
        return device_name
    name = str(device_name).strip()
    if not name:
        return name
    if name == "default":
        if sd is None:
            return "pulse"
        try:
            names = [
                str(d.get("name", "")).strip()
                for d in sd.query_devices()
                if int(d.get("max_output_channels", 0)) > 0
            ]
            names = [n for n in names if n]
            if not names:
                return "pulse"
            virtual = _pick_virtual_output(names)
            if virtual is not None:
                return virtual
            if "pulse" in names:
                return "pulse"
            return names[0]
        except Exception:
            return "pulse"
    lowered = name.lower()
    if ".monitor" in lowered:
        candidate = name[:-len(".monitor")] if lowered.endswith(".monitor") else name.split(".monitor", 1)[0]
        if candidate:
            name = candidate
        is_monitor = True
    else:
        is_monitor = False
    try:
        names = [
            str(d.get("name", "")).strip()
            for d in sd.query_devices()
            if int(d.get("max_output_channels", 0)) > 0
        ]
        names = [n for n in names if n]
        if not names:
            return name
        if name in names:
            return name
        if is_monitor:
            return name
        if "ai-virtual-cam" in lowered or "virtual-cam" in lowered or "virtual" in lowered or "monitor" in lowered:
            if "pulse" in names:
                return "pulse"
            return names[0]
        if name == "pulse" and names:
            if "pulse" in names:
                return "pulse"
            return names[0]
        if "pulse" in names:
            return "pulse"
    except Exception:
        return name
    return name


def _normalize_audio_device_token(value: str) -> str:
    lowered = str(value).lower()
    return re.sub(r"[^a-z0-9]+", "", lowered)


def _audio_device_match_tokens(value: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", str(value).lower())
    return {token for token in tokens if len(token) >= 3 and token not in {"alsa", "input", "output", "analog", "stereo"}}


def _resolve_pulse_device_for_sounddevice(device_name: str, *, kind: str, devices: list[str]) -> str | None:
    if platform.system() != "Linux":
        return None
    lowered = str(device_name).strip().lower()
    if not (lowered.startswith("alsa_input.") or lowered.startswith("alsa_output.") or lowered == AUDIO_VIRTUAL_SOURCE_NAME):
        return None

    desc_map = _audio_device_description_map(kind)
    candidates = [device_name, desc_map.get(device_name, "")]
    compact_candidates = [_normalize_audio_device_token(candidate) for candidate in candidates if candidate]
    compact_candidates = [candidate for candidate in compact_candidates if candidate]
    source_tokens: set[str] = set()
    for candidate in candidates:
        source_tokens.update(_audio_device_match_tokens(candidate))
    if not compact_candidates and not source_tokens:
        return None

    best_device = None
    best_score = 0
    for device in devices:
        compact_device = _normalize_audio_device_token(device)
        if not compact_device:
            continue
        score = 0
        for compact_candidate in compact_candidates:
            if compact_candidate and compact_candidate in compact_device:
                score = max(score, len(compact_candidate))
            elif compact_device and compact_device in compact_candidate:
                score = max(score, len(compact_device))
        device_tokens = _audio_device_match_tokens(device)
        common_tokens = source_tokens.intersection(device_tokens)
        if common_tokens:
            score = max(score, sum(len(token) for token in common_tokens))
        if score > best_score:
            best_score = score
            best_device = device
    return best_device if best_score >= 6 else None


def _coerce_audio_input_device_for_sounddevice(device_name: str) -> str:
    if sd is None:
        return str(device_name).strip()
    name = str(device_name).strip()
    if not name:
        return name
    lowered = name.lower()
    if name.lower() == "default":
        try:
            default_pair = sd.default.device
            default_input_index = int(default_pair[0]) if default_pair and default_pair[0] is not None else -1
            if default_input_index >= 0:
                info = sd.query_devices(default_input_index, kind="input")
                resolved = str(info.get("name", "")).strip()
                if resolved:
                    return resolved
        except Exception:
            pass
        return "default"
    try:
        # 1) exact name first
        sd.query_devices(name, kind="input")
        return name
    except Exception:
        pass

    try:
        devices = [
            str(d.get("name", "")).strip()
            for d in sd.query_devices()
            if int(d.get("max_input_channels", 0)) > 0
        ]
        devices = [d for d in devices if d]
    except Exception:
        return name

    if not devices:
        return name

    # 2) resolve hw token to a concrete sounddevice name
    hw_match = re.search(r"\b(hw:[0-9]+,[0-9]+)\b", name)
    if hw_match is not None:
        hw_token = hw_match.group(1).lower()
        for candidate in devices:
            if hw_token in candidate.lower():
                return candidate

    # 2-1) map Pulse source ID (alsa_input...__source) to hw token when possible
    if lowered.startswith("alsa_input.") or lowered.startswith("alsa_output."):
        # Examples:
        # - alsa_input....__hw_sofhdadsp_6__source -> hw:0,6
        # - alsa_input....__hw_sofhdadsp__source   -> hw:0,0
        m_hw = re.search(r"__hw_[^_]+_([0-9]+)__source$", lowered)
        if m_hw is not None:
            hw_token = f"hw:0,{m_hw.group(1)}"
        else:
            m_hw = re.search(r"__hw_[^_]+__source$", lowered)
            hw_token = "hw:0,0" if m_hw is not None else None
        if hw_token is not None:
            for candidate in devices:
                if hw_token in candidate.lower():
                    return candidate

    # 2-2) map Pulse source ID/description to the PortAudio device name.
    pulse_match = _resolve_pulse_device_for_sounddevice(name, kind="input", devices=devices)
    if pulse_match:
        return pulse_match

    # 2-3) PortAudio may expose Pulse/PipeWire as a single runtime endpoint
    # instead of listing every Pulse source. Use that endpoint for GUI tests.
    if lowered.startswith("alsa_input.") or lowered.endswith(".monitor") or lowered == AUDIO_VIRTUAL_SOURCE_NAME:
        for runtime_name in ("pipewire", "pulse"):
            for candidate in devices:
                if candidate.lower() == runtime_name:
                    return candidate

    # 3) no implicit fallback to arbitrary hardware here: keep configured value
    return name


def _pactl_default_audio_device(kind: str) -> str:
    if platform.system() != "Linux":
        return "default"
    if kind not in {"source", "sink"}:
        return "default"
    try:
        proc = subprocess.run(
            ["pactl", f"get-default-{'source' if kind == 'source' else 'sink'}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=1.5,
        )
    except Exception:
        proc = None
    if proc is not None and proc.returncode == 0:
        default_name = proc.stdout.strip()
        if default_name:
            return default_name

    try:
        proc_list = subprocess.run(
            ["pactl", "list", "short", f"{kind}s"],
            capture_output=True,
            text=True,
            check=False,
            timeout=1.5,
        )
        if proc_list.returncode == 0:
            for line in proc_list.stdout.splitlines():
                parts = line.split("\t")
                if len(parts) < 2:
                    continue
                name = parts[1].strip()
                if not name:
                    continue
                lowered = name.lower()
                if "virtual" in lowered:
                    return name
                if "default" not in lowered:
                    return name
    except Exception:
        return "default"
    return "default"


def _audio_default_input_device() -> str:
    if platform.system() != "Linux":
        return "default"
    if _is_container_runtime():
        pactl_default = _pactl_default_audio_device("source")
        return pactl_default if pactl_default != "default" else "default"

    def _preferred_monitor_source() -> str | None:
        try:
            proc = subprocess.run(
                ["pactl", "list", "short", "sources"],
                capture_output=True,
                text=True,
                check=False,
                timeout=1.5,
            )
            if proc.returncode != 0:
                return None
            names = []
            for line in proc.stdout.splitlines():
                parts = line.split()
                if len(parts) < 2:
                    continue
                names.append(parts[1].strip())
            for candidate in names:
                if candidate == "ai-virtual-cam.monitor":
                    return candidate
            for candidate in names:
                if candidate.endswith(".monitor"):
                    return candidate
        except Exception:
            return None
        return None

    monitor = _preferred_monitor_source()
    if monitor is not None:
        return monitor

    if sd is None:
        pactl_default = _pactl_default_audio_device("source")
        return pactl_default if pactl_default != "default" else "default"
    try:
        default_input = sd.default.device[0] if sd.default.device is not None else None
        if isinstance(default_input, int):
            device = sd.query_devices(default_input)
            if device and int(device.get("max_input_channels", 0)) > 0:
                name = str(device.get("name", "")).strip()
                if name:
                    return name
    except Exception:
        pactl_default = _pactl_default_audio_device("source")
        return pactl_default if pactl_default != "default" else "default"
    try:
        for device in sd.query_devices():
            name = str(device.get("name", ""))
            if not name:
                continue
            if int(device.get("max_input_channels", 0)) <= 0:
                continue
            lowered = name.lower()
            if "ai-virtual-cam" in lowered or "virtual-cam" in lowered or "virtual" in lowered:
                return name
            if lowered not in {"default"}:
                return name
    except Exception:
        pactl_default = _pactl_default_audio_device("source")
        return pactl_default if pactl_default != "default" else "default"
    pactl_default = _pactl_default_audio_device("source")
    return pactl_default if pactl_default != "default" else "default"


def _audio_device_candidates(kind: str) -> list[str]:
    print(f"[avc] 오디오 {kind} 디바이스 후보 수집 시작 (sd_imported={sd is not None})", flush=True)
    values: list[str] = ["default"]
    seen = {"default"}

    channel_key = "max_input_channels" if kind == "input" else "max_output_channels"
    print(
        f"[avc] 오디오 {kind} 디바이스 채널키={channel_key}",
        flush=True,
    )
    if sd is not None and not _is_container_runtime():
        try:
            for device in sd.query_devices():
                name = str(device.get("name", "")).strip()
                if not name:
                    continue
                if int(device.get(channel_key, 0)) <= 0:
                    continue
                if name not in seen:
                    seen.add(name)
                    values.append(name)
                    print(f"[avc] 오디오 {kind} 후보(sounddevice): {name}", flush=True)
        except Exception:
            print(f"[avc] 오디오 {kind} sounddevice 조회 실패: 예외 발생", flush=True)
            pass

    if platform.system() == "Darwin":
        macos_virtual_candidates = ["BlackHole 2ch", "BlackHole 16ch", "BlackHole 64ch"]
        for candidate in macos_virtual_candidates:
            if candidate not in seen:
                seen.add(candidate)
                values.append(candidate)
                print(f"[avc] 오디오 {kind} 후보(macos-virtual): {candidate}", flush=True)

    if platform.system() == "Linux":
        pactl_kind = "source" if kind == "input" else "sink"
        try:
            proc = subprocess.run(
                ["pactl", "list", "short", f"{pactl_kind}s"],
                capture_output=True,
                text=True,
                check=False,
                timeout=1.5,
            )
            if proc.returncode == 0:
                for line in proc.stdout.splitlines():
                    parts = line.split()
                    if len(parts) < 2:
                        continue
                    dev_id = parts[1].strip()
                    if not dev_id:
                        continue
                    if dev_id not in seen:
                        seen.add(dev_id)
                        values.append(dev_id)
                        print(f"[avc] 오디오 {kind} 후보(pactl): {dev_id}", flush=True)
            else:
                print(f"[avc] 오디오 {kind} pactl 조회 실패: rc={proc.returncode}", flush=True)
        except Exception:
            print(f"[avc] 오디오 {kind} pactl 조회 실패: 예외 발생", flush=True)

    if not values:
        values.append("default")
        print(f"[avc] 오디오 {kind} 후보가 비어 fallback 'default' 추가", flush=True)
    print(f"[avc] 오디오 {kind} 총 후보 수: {len(values)}", flush=True)
    return values


def _audio_input_device_candidates() -> list[str]:
    return _audio_device_candidates("input")


def _audio_output_device_candidates() -> list[str]:
    return _audio_device_candidates("output")


def _audio_device_description_map(kind: str) -> dict[str, str]:
    if platform.system() != "Linux":
        return {}
    if kind not in {"input", "output"}:
        return {}
    target = "sources" if kind == "input" else "sinks"
    try:
        env = dict(__import__("os").environ)
        env["LC_ALL"] = "C"
        env["LANG"] = "C"
        proc = subprocess.run(
            ["pactl", "list", target],
            capture_output=True,
            text=True,
            check=False,
            timeout=2.5,
            env=env,
        )
        if proc.returncode != 0:
            return {}
    except Exception:
        return {}

    mapping: dict[str, str] = {}
    current_name: str | None = None
    current_desc: str | None = None
    for raw_line in proc.stdout.splitlines():
        line = raw_line.strip()
        if line.startswith("Name:"):
            if current_name and current_desc:
                mapping[current_name] = current_desc
            current_name = line.split(":", 1)[1].strip()
            current_desc = None
            continue
        if line.startswith("Description:"):
            current_desc = line.split(":", 1)[1].strip()
            continue
        if not line and current_name and current_desc:
            mapping[current_name] = current_desc
            current_name = None
            current_desc = None
    if current_name and current_desc:
        mapping[current_name] = current_desc
    return mapping


def _audio_device_display_values(kind: str, raw_values: list[str]) -> tuple[list[str], dict[str, str]]:
    desc_map = _audio_device_description_map(kind)
    display_values: list[str] = []
    display_to_raw: dict[str, str] = {}
    for raw in raw_values:
        base = str(raw).strip()
        if not base:
            continue
        desc = desc_map.get(base, "")
        display = f"{desc} | {base}" if desc else base
        if display in display_to_raw:
            continue
        display_values.append(display)
        display_to_raw[display] = base
    return display_values, display_to_raw


def _audio_device_raw_from_display(value: str, mapping: dict[str, str]) -> str:
    key = str(value).strip()
    if not key:
        return key
    mapped = mapping.get(key)
    if mapped:
        return mapped
    if " | " in key:
        return key.rsplit(" | ", 1)[-1].strip()
    return key


def _can_capture_exact_pulse_source(device_name: str) -> bool:
    if platform.system() != "Linux":
        return False
    name = str(device_name).strip()
    if not name or name.lower() == "default":
        return False
    lowered = name.lower()
    return lowered.startswith("alsa_input.") or lowered.endswith(".monitor") or lowered == AUDIO_VIRTUAL_SOURCE_NAME


def _available_input_meter_devices() -> list[str]:
    values: list[str] = []
    if sd is not None:
        try:
            values.extend(
                str(d.get("name", "")).strip()
                for d in sd.query_devices()
                if int(d.get("max_input_channels", 0)) > 0 and str(d.get("name", "")).strip()
            )
        except Exception:
            pass
    if platform.system() == "Linux":
        try:
            values.extend(name for _idx, name, _rest in _pactl_short_entries("source") if name)
        except Exception:
            pass
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _parse_video_device_number(device_path: str) -> str | None:
    value = device_path.strip()
    if not value.startswith("/dev/video"):
        return None
    tail = value[len("/dev/video"):]
    if not tail.isdigit():
        return None
    return tail


def _pactl_short_entries(kind: str) -> list[tuple[str, str, str]]:
    if platform.system() != "Linux":
        return []
    try:
        proc = _run_cmd(["pactl", "list", "short", f"{kind}s"], check=False, timeout=1.5)
    except Exception as exc:
        _log(f"pactl list short {kind}s failed: {exc}")
        return []
    if proc.returncode != 0:
        return []
    items: list[tuple[str, str, str]] = []
    for raw in proc.stdout.splitlines():
        parts = raw.split()
        if len(parts) < 3:
            continue
        items.append((parts[0], parts[1], " ".join(parts[2:])))
    return items


def _format_pulse_runtime_entry_names(entries: list[tuple[str, str, str]], *, limit: int = 8) -> str:
    names = [entry_name for _idx, entry_name, _rest in entries if entry_name.strip()]
    if not names:
        return "(none)"
    preview = names[:limit]
    suffix = "" if len(names) <= limit else f" ... (+{len(names) - limit} more)"
    return ", ".join(preview) + suffix


def _validate_pulse_runtime_device(kind: str, device_name: str) -> None:
    if platform.system() != "Linux":
        return
    name = str(device_name).strip()
    if not name or name.lower() == "default":
        raise ValueError(
            f"audio {kind} device는 Linux runtime에서 명시값이 필요합니다. "
            f"현재값='{device_name}'. config에서 실제 장치 ID를 선택하세요."
        )
    entries = _pactl_short_entries("source" if kind == "input" else "sink")
    if not entries:
        _log(
            f"audio {kind} device runtime validation skipped: "
            "pactl list short returned no entries"
        )
        return
    runtime_kind = "source" if kind == "input" else "sink"
    names = [entry_name for _idx, entry_name, _rest in entries if entry_name.strip()]
    if name not in names:
        available_names = _format_pulse_runtime_entry_names(entries)
        virtual_hint = ""
        if "ai-virtual-cam" in name:
            expected_partner = "ai-virtual-cam-mic / ai-virtual-cam.monitor" if kind == "input" else "ai-virtual-cam"
            virtual_hint = (
                " 가상 오디오 힌트: "
                f"input에는 source/monitor ID를, output에는 sink ID를 써야 합니다. expected={expected_partner}."
            )
        _log(
            "audio runtime validation failed: "
            f"kind={kind} runtime_kind={runtime_kind} requested='{name}' "
            f"available={available_names}{virtual_hint}"
        )
        raise ValueError(
            f"audio {kind} device가 Pulse runtime에 존재하지 않습니다: '{name}'. "
            f"runtime {runtime_kind} 목록={available_names}. "
            f"config에서 Pulse 장치 ID(source/sink)를 다시 선택하세요."
        )


def _resolve_and_validate_audio_runtime_devices(
    audio_input_display: str,
    audio_output_display: str,
    input_display_to_raw: dict[str, str] | None = None,
    output_display_to_raw: dict[str, str] | None = None,
) -> tuple[str, str]:
    raw_audio_input = _audio_device_raw_from_display(
        audio_input_display.strip(),
        input_display_to_raw or {},
    )
    raw_audio_output = _audio_device_raw_from_display(
        audio_output_display.strip(),
        output_display_to_raw or {},
    )
    _validate_pulse_runtime_device("input", raw_audio_input)
    _validate_pulse_runtime_device("output", raw_audio_output)
    return raw_audio_input, raw_audio_output


def _audio_sink_exists(name: str) -> bool:
    return any(sink_id == name for _, sink_id, _ in _pactl_short_entries("sink"))


def _audio_source_exists(name: str) -> bool:
    return any(source_id == name for _, source_id, _ in _pactl_short_entries("source"))


def _get_module_ids(module_name: str, arg_key: str, name: str) -> list[str]:
    ids: list[str] = []
    for mod_id, _module, args in _pactl_short_entries("module"):
        if not args:
            continue
        if module_name not in _module:
            continue
        if f"{arg_key}={name}" not in args:
            continue
        ids.append(mod_id)
    return ids


def _get_audio_sink_module_ids(name: str) -> list[str]:
    return _get_module_ids("module-null-sink", "sink_name", name)


def _get_audio_source_module_ids(name: str) -> list[str]:
    return _get_module_ids("module-remap-source", "source_name", name)
