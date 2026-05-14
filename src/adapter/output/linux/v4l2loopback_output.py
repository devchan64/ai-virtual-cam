import os
import re
from pathlib import Path
import shutil
import subprocess
import time
from dataclasses import dataclass

import cv2
import numpy as np

from src.adapter.output.base import OutputSink
from src.domain.config import OutputCameraConfig


@dataclass(frozen=True)
class _SelectedV4L2Profile:
    pixel_format: str
    width: int
    height: int


def _read_v4l2_node_name(video_path: str) -> str:
    try:
        return (
            (Path("/sys/class/video4linux") / Path(video_path).name / "name")
            .read_text(encoding="utf-8")
            .strip()
        )
    except Exception:
        return ""


def _node_is_virtual_loopback(name: str) -> bool:
    lowered = name.lower()
    return "v4l2loopback" in lowered or "virtual" in lowered


def _fourcc_to_ffmpeg_pix_fmt(fourcc: str) -> str | None:
    mapping = {
        "YUYV": "yuyv422",
        "YU12": "yuv420p",
        "RGB3": "rgb24",
        "BGR3": "bgr24",
        "NV12": "nv12",
    }
    return mapping.get(fourcc.upper())


def _parse_v4l2_format_output(text: str) -> dict[str, set[tuple[int, int]]]:
    formats: dict[str, set[tuple[int, int]]] = {}
    current_fourcc: str | None = None
    for line in text.splitlines():
        m_fmt = re.search(r"'([A-Za-z0-9]{4})'", line)
        if m_fmt:
            current_fourcc = m_fmt.group(1)
            formats.setdefault(current_fourcc, set())
            continue

        m_size = re.search(r"Size:\s+Discrete\s+(\d+)x(\d+)", line)
        if m_size and current_fourcc:
            width = int(m_size.group(1))
            height = int(m_size.group(2))
            if width > 0 and height > 0:
                formats.setdefault(current_fourcc, set()).add((width, height))
            continue

        m_step = re.search(
            r"Size:\s+Stepwise\s+(\d+)x(\d+)\s+-\s+(\d+)x(\d+)\s+\(\s*(\d+)x(\d+)\s*\)",
            line,
        )
        if m_step and current_fourcc:
            min_w, min_h, max_w, max_h, step_w, step_h = map(int, m_step.groups())
            if 0 < min_w <= max_w and 0 < min_h <= max_h:
                for candidate in ((min_w, min_h), (max_w, max_h)):
                    formats.setdefault(current_fourcc, set()).add(candidate)
                formats.setdefault(current_fourcc, set()).update(
                    {(min_w, max_h), (max_w, min_h)}
                )
            elif 0 < max_w and 0 < max_h:
                formats.setdefault(current_fourcc, set()).add((max_w, max_h))
            continue

        # Fallback: parse any explicit WxH tuple that appears under a format section.
        m_any = re.search(r"(\d+)x(\d+)", line)
        if not m_any or not current_fourcc:
            continue
        width = int(m_any.group(1))
        height = int(m_any.group(2))
        if width > 0 and height > 0:
            formats.setdefault(current_fourcc, set()).add((width, height))
    return formats


def _probe_v4l2_formats(device_path: str) -> dict[str, set[tuple[int, int]]]:
    formats: dict[str, set[tuple[int, int]]] = {}
    try:
        proc = subprocess.run(
            ["v4l2-ctl", "--device", device_path, "--list-formats-ext"],
            capture_output=True,
            text=True,
            check=False,
            timeout=1.5,
        )
    except Exception:
        return formats
    if proc.returncode != 0:
        return formats

    formats = _parse_v4l2_format_output(proc.stdout)
    return formats

def _probe_v4l2_output_formats(device_path: str) -> tuple[dict[str, set[tuple[int, int]]], str, bool]:
    """Probe V4L2 VIDEO OUTPUT formats.

    Returns tuple(formats, detail, available) where available indicates whether the
    device supports querying output format list at all.
    """
    try:
        proc = subprocess.run(
            ["v4l2-ctl", "--device", device_path, "--list-formats-out"],
            capture_output=True,
            text=True,
            check=False,
            timeout=1.5,
        )
    except FileNotFoundError:
        return {}, "v4l2-ctl not installed", False
    except Exception as exc:  # pragma: no cover
        return {}, f"failed to run v4l2-ctl output probe: {exc}", False

    if proc.returncode != 0:
        message = ((proc.stderr or proc.stdout) or "").strip()
        if "not a video output device" in message.lower():
            return {}, f"not a video output device: {message}", False
        return {}, f"v4l2-ctl exit={proc.returncode}: {message or 'no detail'}", False

    raw_formats = _parse_v4l2_format_output(proc.stdout)
    if raw_formats:
        return raw_formats, "output format list available", True
    return {}, "output format list empty", True


def _resolve_v4l2_output_pix_fmt(
    device_path: str,
    width: int,
    height: int,
    preferred: list[str],
) -> _SelectedV4L2Profile:
    fallback = preferred[0] if preferred else "yuv420p"
    raw_formats, out_detail, out_available = _probe_v4l2_output_formats(device_path)
    if out_available and not raw_formats:
        print(
            f"[output] Warning: v4l2 output format list empty for {device_path}. detail={out_detail}. "
            f"Proceeding with fallback pixel format {fallback} (output may require manual setup).",
            flush=True,
        )
    elif out_available is False:
        print(
            f"[output] Warning: V4L2 output capability probe unavailable for {device_path}: {out_detail}. "
            f"Proceeding with fallback pixel format {fallback}.",
            flush=True,
        )
    if not raw_formats:
        print(
            f"[output] Warning: No inspectable v4l2 format info for {device_path}. "
            f"Proceeding with fallback pixel format {fallback} (install v4l2-ctl for validation).",
            flush=True,
        )
        return _SelectedV4L2Profile(pixel_format=fallback, width=width, height=height)

    parsed = [
        (_fourcc_to_ffmpeg_pix_fmt(fourcc), fourcc, sizes)
        for fourcc, sizes in raw_formats.items()
        if _fourcc_to_ffmpeg_pix_fmt(fourcc) is not None
    ]
    supported: dict[str, set[tuple[int, int]]] = {
        pix_fmt: sizes for pix_fmt, _fourcc, sizes in parsed if pix_fmt is not None
    }
    if not supported:
        print(
            f"[output] Warning: No supported mapped v4l2 pix_fmt found for {device_path}. "
            f"Mapped formats={sorted(raw_formats)}. Falling back to {fallback}.",
            flush=True,
        )
        return _SelectedV4L2Profile(pixel_format=fallback, width=width, height=height)

    # Prefer configured order to keep behavior deterministic.
    for pix_fmt in preferred:
        if pix_fmt not in supported:
            continue
        if not supported[pix_fmt]:
            return _SelectedV4L2Profile(pixel_format=pix_fmt, width=width, height=height)
        if (width, height) in supported[pix_fmt]:
            return _SelectedV4L2Profile(pixel_format=pix_fmt, width=width, height=height)
        sizes = sorted(supported[pix_fmt], key=lambda size: abs(size[0] - width) + abs(size[1] - height))
        closest_w, closest_h = sizes[0]
        print(
            f"[output] Warning: requested output size {width}x{height} not supported for {pix_fmt} on {device_path}. "
            f"Using closest supported size {closest_w}x{closest_h}.",
            flush=True,
        )
        return _SelectedV4L2Profile(pixel_format=pix_fmt, width=closest_w, height=closest_h)

    # Device exposes formats, but not the desired size.
    size_hint = sorted({f"{w}x{h}" for sizes in supported.values() for w, h in sizes})
    print(
        f"[output] Warning: v4l2 device {device_path} may not support {width}x{height}. "
        f"Supported sizes: {size_hint}. Proceeding with fallback {fallback}.",
        flush=True,
    )
    return _SelectedV4L2Profile(pixel_format=fallback, width=width, height=height)


def _has_v4l2_capability(capability_text: str, feature: str) -> bool:
    return feature.lower() in (capability_text or "").lower()


def _read_v4l2_capability_text(video_path: str) -> tuple[str, str]:
    """Prefer `-D` for stable capability query. Fallback to `--all`."""
    try:
        proc = subprocess.run(
            ["v4l2-ctl", "-D", "--device", video_path],
            capture_output=True,
            text=True,
            check=False,
            timeout=1.5,
        )
        text = ((proc.stdout or "") + (proc.stderr or "")).lower()
        if text.strip():
            return text, "v4l2-ctl -D"
    except FileNotFoundError:
        return "", "v4l2-ctl not installed"
    except Exception:
        pass

    try:
        proc = subprocess.run(
            ["v4l2-ctl", "--all", "--device", video_path],
            capture_output=True,
            text=True,
            check=False,
            timeout=1.5,
        )
        text = ((proc.stdout or "") + (proc.stderr or "")).lower()
        return text, "v4l2-ctl --all"
    except FileNotFoundError:
        return "", "v4l2-ctl not installed"
    except Exception as exc:  # pragma: no cover
        return "", f"v4l2-ctl capability check failed: {exc}"


def _v4l2_output_capable(video_path: str) -> tuple[bool | None, str]:
    formats, detail, available = _probe_v4l2_output_formats(video_path)
    # Prefer output-format probe plus capability flags from --all.
    # Some non-loopback devices may expose `--list-formats-ext out`, so we must
    # verify Video Output capability explicitly.
    capability_stdout, source = _read_v4l2_capability_text(video_path)
    if not capability_stdout:
        return None, f"{source}; cannot verify capabilities"

    has_output_cap = _has_v4l2_capability(capability_stdout, "video output")
    has_capture = _has_v4l2_capability(capability_stdout, "video capture")

    if not has_output_cap:
        if has_capture:
            if not available:
                return None, f"{source}: capture capability visible, output unresolved"
            return False, "device reports Video Capture only"
        if not available:
            return None, f"capability unknown ({source}; detail={detail})"
        return False, "device does not report Video Output in capabilities"

    if not formats:
        if not available:
            return True, f"device reports Video Output in capabilities (via --all), format probe unavailable: {detail}"
        return (
            True,
            "device reports Video Output capability (via --all), but output format list is empty",
        )

    return True, "device reports Video Output capability (via format probe)"


def _v4l2_capture_capable(video_path: str) -> tuple[bool | None, str]:
    output, source = _read_v4l2_capability_text(video_path)
    if not output:
        return None, f"{source}; cannot verify capabilities"

    if _has_v4l2_capability(output, "video capture"):
        return True, f"device reports Video Capture capability ({source})"
    return None, "device does not report Video Capture in capabilities"


def _resolve_v4l2_device(configured: str) -> str:
    configured_path = Path(configured)
    if not configured_path.exists():
        raise RuntimeError(
            f"Configured v4l2 device not found: {configured}. "
            "Create the loopback device and set output device explicitly."
        )

    def _log_resolved(path: str, message: str) -> str:
        resolved_path = str(Path(path))
        print(f"[output] {message}: {resolved_path}", flush=True)
        return resolved_path

    configured_str = str(configured_path)
    output_capable, output_detail = _v4l2_output_capable(configured_str)
    capture_capable, capture_detail = _v4l2_capture_capable(configured_str)

    if output_capable is True and capture_capable is True:
        node_name = _read_v4l2_node_name(configured_str)
        if node_name and not _node_is_virtual_loopback(node_name):
            print(
                f"[output] configured v4l2 device is not virtual loopback: {configured_str} name='{node_name}'",
                flush=True,
            )
        else:
            print(f"[output] configured v4l2 device resolved: {configured_str}", flush=True)
        return configured_str
    # In exclusive_caps mode, capture capability may not be visible before/while
    # producer negotiation. If output side is verified, allow startup.
    if output_capable is True and capture_capable is None:
        print(
            f"[output] configured v4l2 device resolved with output capability: {configured_str} "
            f"(capture capability unresolved: {capture_detail})",
            flush=True,
        )
        return configured_str

    if output_capable is False or capture_capable is False:
        print(
            f"[output] configured v4l2 device is not webcam-capable: {configured_str}. "
            f"output={output_detail}. capture={capture_detail}.",
            flush=True,
        )

    if output_capable is None or capture_capable is None:
        print(
            f"[output] Warning: configured v4l2 device capability is not fully verifiable: {configured_str}. "
            f"output={output_detail}. capture={capture_detail}. Falling back to configured path.",
            flush=True,
        )
        return _log_resolved(configured_str, "configured v4l2 device resolved (capability unresolved)")

    # Configured device exists but is not webcam-capable. Try only nodes that are
    # positively verified as capture+output capable.
    root = Path("/sys/class/video4linux")
    confirmed: list[tuple[str, str]] = []
    if root.exists():
        for entry in sorted(root.glob("video*")):
            dev_path = str(Path("/dev") / entry.name)
            if not Path(dev_path).exists():
                continue
            output_capable, _ = _v4l2_output_capable(dev_path)
            capture_capable, _ = _v4l2_capture_capable(dev_path)
            if output_capable is not True or capture_capable is not True:
                continue
            node_name = _read_v4l2_node_name(dev_path)
            confirmed.append((dev_path, node_name))

    candidates = confirmed
    preferred = [path for path, name in candidates if _node_is_virtual_loopback(name)]
    fallback = preferred[0] if preferred else None
    if fallback is None:
        print(
            f"[output] Warning: Configured v4l2 device is not webcam-capable: {configured_str}. "
            f"output={output_detail}, capture={capture_detail}.",
            flush=True,
        )
        raise RuntimeError(
            "Configured v4l2 device is not usable for webcam output, and no virtual v4l2loopback device was found. "
            "Only virtual loopback nodes are allowed as output targets. "
            "Create the virtual camera again in config-gui and set output.devicePath to that /dev/videoN."
        )

    print(
        f"[output] Configured v4l2 device is not webcam-capable: {configured_str} ({output_detail}, {capture_detail}). "
        f"auto-selected output device {fallback}.",
        flush=True,
    )
    return _log_resolved(fallback, "resolved output-capable v4l2 device")


def _iter_v4l2_devices() -> list[str]:
    root = Path("/sys/class/video4linux")
    if not root.exists():
        return []
    devices: list[str] = []
    for entry in sorted(root.glob("video*")):
        if not entry.is_dir():
            continue
        dev_path = Path("/dev") / entry.name
        if dev_path.exists():
            devices.append(str(dev_path))
    return devices


def _read_nonblocking_stderr(proc: subprocess.Popen[bytes], max_bytes: int = 2048) -> str:
    if proc.stderr is None:
        return ""
    try:
        import os

        stderr_fd = proc.stderr.fileno()
        os.set_blocking(stderr_fd, False)
        data = os.read(stderr_fd, max_bytes)
        if not data:
            return ""
        return data.decode("utf-8", errors="ignore").strip()
    except BlockingIOError:
        return ""
    except Exception:
        return ""


def _ffmpeg_pix_fmt_to_fourcc(pixel_format: str) -> str | None:
    mapping = {
        "yuyv422": "YUYV",
        "yuv420p": "YU12",
        "rgb24": "RGB3",
        "bgr24": "BGR3",
        "nv12": "NV12",
    }
    return mapping.get(pixel_format.lower())


def _set_v4l2_device_format(device_path: str, width: int, height: int, pixel_format: str) -> tuple[bool, str]:
    fourcc = _ffmpeg_pix_fmt_to_fourcc(pixel_format)
    if fourcc is None:
        return False, f"format_preseed_skipped_unmapped_pix_fmt={pixel_format}"
    payload = f"width={width},height={height},pixelformat={fourcc}"
    args_list = [
        ["v4l2-ctl", "--device", device_path, f"--set-fmt-video-out={payload}"],
        ["v4l2-ctl", "--device", device_path, f"--set-fmt-video={payload}"],
    ]
    last_error = ""
    for args in args_list:
        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                check=False,
                timeout=2.0,
            )
        except FileNotFoundError:
            return False, "v4l2-ctl not installed"
        except Exception as exc:
            return False, f"v4l2-ctl set format failed: {exc}"

        if proc.returncode == 0:
            return True, "format set"

        stderr = (proc.stderr or proc.stdout or "").strip()
        last_error = f"v4l2-ctl exit={proc.returncode} {stderr}".strip()

    return False, last_error


def _recover_v4l2_device_runtime_state(
    device_path: str,
    width: int,
    height: int,
    fps: int,
    pixel_format: str,
) -> tuple[bool, str]:
    """Best-effort runtime recovery for stale loopback state after abrupt stop/start."""
    fourcc = _ffmpeg_pix_fmt_to_fourcc(pixel_format) or "YU12"
    caps = f"{fourcc}:{width}x{height}@{fps}"
    gst_fmt_map = {
        "YU12": "I420",
        "YUYV": "YUY2",
        "BGR3": "BGR",
        "RGB3": "RGB",
        "NV12": "NV12",
    }
    gst_fmt = gst_fmt_map.get(fourcc, "I420")
    gst_caps = f"video/x-raw,format={gst_fmt},width={width},height={height},framerate={fps}/1"
    notes: list[str] = []
    used = False

    ctl = shutil.which("v4l2loopback-ctl")
    if ctl is not None:
        used = True
        def _try_ctl_variants(variants: list[list[str]]) -> tuple[bool, str]:
            last = "unknown"
            for args in variants:
                try:
                    proc = subprocess.run(
                        args,
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=2.0,
                    )
                except Exception as exc:  # pragma: no cover
                    last = f"exception: {exc}"
                    continue
                if proc.returncode == 0:
                    return True, "ok"
                last = (proc.stderr or proc.stdout or "").strip() or f"rc={proc.returncode}"
            return False, last

        try:
            ok_caps = False
            detail_caps = "unknown"
            caps_candidates = [caps, gst_caps, "any"]
            for candidate in caps_candidates:
                ok_caps, detail_caps = _try_ctl_variants(
                    [
                        [ctl, "set-caps", device_path, candidate],
                        [ctl, "set-caps", candidate, device_path],
                    ]
                )
                if ok_caps:
                    caps = candidate
                    break
            if ok_caps:
                notes.append(f"set-caps ok ({caps})")
            else:
                notes.append(f"set-caps failed {detail_caps}")
        except Exception as exc:  # pragma: no cover
            notes.append(f"set-caps exception: {exc}")

        try:
            ok_fps, detail_fps = _try_ctl_variants(
                [
                    [ctl, "set-fps", str(fps), device_path],
                    [ctl, "set-fps", device_path, str(fps)],
                ]
            )
            if ok_fps:
                notes.append(f"set-fps ok ({fps})")
            else:
                notes.append(f"set-fps failed {detail_fps}")
        except Exception as exc:  # pragma: no cover
            notes.append(f"set-fps exception: {exc}")

    ok, detail = _set_v4l2_device_format(device_path, width, height, pixel_format)
    notes.append(f"set-fmt {'ok' if ok else 'failed'}: {detail}")
    if used or ok:
        return True, "; ".join(notes)
    return False, "recovery tools unavailable"


def _recreate_v4l2loopback_device_noninteractive(device_path: str) -> tuple[bool, str]:
    """Try recreating v4l2loopback module without blocking for password input."""
    video_no = None
    m = re.match(r"^/dev/video(\d+)$", device_path)
    if m:
        video_no = m.group(1)
    if video_no is None:
        return False, f"cannot parse video number from device path: {device_path}"

    notes: list[str] = []
    try:
        proc = subprocess.run(
            ["sudo", "-n", "modprobe", "-r", "v4l2loopback"],
            capture_output=True,
            text=True,
            check=False,
            timeout=4.0,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            notes.append(f"modprobe -r rc={proc.returncode} {err}")
        else:
            notes.append("modprobe -r ok")
    except Exception as exc:  # pragma: no cover
        notes.append(f"modprobe -r exception: {exc}")

    try:
        subprocess.run(
            ["sudo", "-n", "modprobe", "videodev"],
            capture_output=True,
            text=True,
            check=False,
            timeout=4.0,
        )
    except Exception:
        pass

    try:
        proc = subprocess.run(
            [
                "sudo",
                "-n",
                "modprobe",
                "v4l2loopback",
                "devices=1",
                f"video_nr={video_no}",
                "card_label=ai-virtual-cam",
                "exclusive_caps=1",
                "max_buffers=2",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=4.0,
        )
    except Exception as exc:  # pragma: no cover
        return False, "; ".join(notes + [f"modprobe load exception: {exc}"])

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        return False, "; ".join(notes + [f"modprobe load rc={proc.returncode} {err}"])

    if not Path(device_path).exists():
        return False, "; ".join(notes + [f"device missing after recreate: {device_path}"])
    return True, "; ".join(notes + ["modprobe load ok"])


def _probe_ffmpeg_profile(proc: subprocess.Popen[bytes], width: int, height: int) -> tuple[bool, str]:
    probe_frame = bytes(width * height * 3)
    try:
        proc.stdin.write(probe_frame)
    except Exception as exc:  # pragma: no cover
        return False, f"probe_write_failed: {exc}"

    try:
        proc.stdin.flush()
    except Exception:
        pass

    for _ in range(40):
        time.sleep(0.05)
        if proc.poll() is not None:
            return False, f"probe_exited_early: {_read_nonblocking_stderr(proc)}"
        stderr_hint = _read_nonblocking_stderr(proc)
        if "Invalid argument" in stderr_hint or "Could not write header for output file" in stderr_hint:
            return False, f"probe_stderr: {stderr_hint}"

    return True, ""


class V4L2LoopbackOutput(OutputSink):
    """Linux v4l2loopback output scaffold.

    This sends BGR frames to ffmpeg stdin and lets ffmpeg publish to a v4l2 device.
    """

    def __init__(self, config: OutputCameraConfig) -> None:
        self._config = config
        self._device_path = _resolve_v4l2_device(config.devicePath)
        self._ffmpeg_format = "yuv420p"
        self._proc: subprocess.Popen[bytes] | None = None
        self._proc = self._spawn_ffmpeg(config, self._device_path)
        self._frames_sent = 0
        print(
            f"[output] v4l2loopback opened: {config.width}x{config.height}@{config.fps} -> {self._device_path}",
            flush=True,
        )
        print(f"[output] v4l2loopback actual device: {self._device_path}", flush=True)

    def _make_ffmpeg_cmd(
        self,
        config: OutputCameraConfig,
        device_path: str,
        pixel_format: str,
        width: int,
        height: int,
    ) -> list[str]:
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-s",
            f"{width}x{height}",
            "-r",
            str(config.fps),
            "-i",
            "-",
            "-an",
            "-vf",
            f"format=pix_fmts={pixel_format}",
            "-s:v",
            f"{width}x{height}",
            "-r",
            str(config.fps),
            "-vcodec",
            "rawvideo",
            "-f",
            "v4l2",
            device_path,
        ]
        return cmd

    def _spawn_ffmpeg(
        self, config: OutputCameraConfig, device_path: str
    ) -> subprocess.Popen[bytes]:
        if os.name != "posix":
            raise RuntimeError("v4l2loopback backend is Linux-only.")
        if not os.path.exists(device_path):
            raise RuntimeError(
                f"v4l2 output device not found: {device_path}\n"
                "Run './bin/avc setup' and ensure v4l2loopback device is created."
            )
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            raise RuntimeError("ffmpeg not found. Run './bin/avc setup' first.")

        preferred_formats = [self._ffmpeg_format, "yuv420p", "rgb24", "bgr24", "nv12"]
        selected = _resolve_v4l2_output_pix_fmt(device_path, config.width, config.height, preferred_formats)
        attempted_profiles: list[_SelectedV4L2Profile] = []
        emitted_formats: set[tuple[str, int, int]] = set()
        ordered_formats = [selected.pixel_format] + preferred_formats
        for preferred in ordered_formats:
            profile = _SelectedV4L2Profile(
                pixel_format=preferred,
                width=selected.width,
                height=selected.height,
            )
            key = (profile.pixel_format, profile.width, profile.height)
            if key in emitted_formats:
                continue
            emitted_formats.add(key)
            attempted_profiles.append(profile)

        last_error = ""
        for recover_round in (0, 1, 2):
            if recover_round == 1:
                recovered, detail = _recover_v4l2_device_runtime_state(
                    device_path,
                    selected.width,
                    selected.height,
                    int(config.fps),
                    selected.pixel_format,
                )
                print(
                    f"[output] v4l2loopback startup recovery {'applied' if recovered else 'skipped'}: {detail}",
                    flush=True,
                )
            elif recover_round == 2:
                recreated, detail = _recreate_v4l2loopback_device_noninteractive(device_path)
                print(
                    f"[output] v4l2loopback module recreate {'applied' if recreated else 'skipped'}: {detail}",
                    flush=True,
                )
            for profile in attempted_profiles:
                for enforce_output_pix_fmt in (True, False):
                    if enforce_output_pix_fmt and not Path(device_path).exists():
                        continue
                    cmd = self._make_ffmpeg_cmd(
                        config,
                        device_path,
                        profile.pixel_format,
                        profile.width,
                        profile.height,
                    )
                    cmd[0] = ffmpeg
                    mode = "strict" if enforce_output_pix_fmt else "auto"
                    if enforce_output_pix_fmt:
                        success, detail = _set_v4l2_device_format(
                            device_path,
                            profile.width,
                            profile.height,
                            profile.pixel_format,
                        )
                        if not success:
                            print(
                                f"[output] v4l2loopback strict mode skipped for pix_fmt={profile.pixel_format} "
                                f"size={profile.width}x{profile.height}: {detail}",
                                flush=True,
                            )
                            continue
                        print(
                            f"[output] v4l2loopback strict mode pre-seeded format for pix_fmt={profile.pixel_format} "
                            f"size={profile.width}x{profile.height}",
                            flush=True,
                        )
                    try:
                        proc = subprocess.Popen(
                            cmd,
                            stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE,
                        )
                    except Exception as exc:  # pragma: no cover
                        last_error = f"Failed to start ffmpeg for v4l2 output: {exc}"
                        print(
                            f"[output] v4l2loopback ffmpeg start failure mode={mode} "
                            f"pix_fmt={profile.pixel_format} size={profile.width}x{profile.height}: {last_error}",
                            flush=True,
                        )
                        continue

                    time.sleep(0.25)
                    if proc.poll() is not None:
                        stderr_msg = ""
                        if proc.stderr is not None:
                            try:
                                stderr_msg = proc.stderr.read().decode("utf-8", errors="ignore").strip()
                            except Exception:
                                stderr_msg = ""
                        last_error = (
                            f"selected pix_fmt={profile.pixel_format} selected size={profile.width}x{profile.height}. "
                            f"mode={mode}. return_code={proc.returncode}. stderr={stderr_msg or '<empty>'}"
                        )
                        print(
                            f"[output] v4l2loopback ffmpeg start failure mode={mode} "
                            f"pix_fmt={profile.pixel_format} size={profile.width}x{profile.height}: {last_error}",
                            flush=True,
                        )
                        continue

                    ok, probe_error = _probe_ffmpeg_profile(proc, profile.width, profile.height)
                    if not ok:
                        stderr_msg = probe_error or _read_nonblocking_stderr(proc)
                        last_error = (
                            f"selected pix_fmt={profile.pixel_format} selected size={profile.width}x{profile.height}. "
                            f"mode={mode}. {stderr_msg or 'probe failed'}"
                        )
                        print(
                            f"[output] v4l2loopback ffmpeg profile probe failure mode={mode} "
                            f"pix_fmt={profile.pixel_format} size={profile.width}x{profile.height}: {last_error}",
                            flush=True,
                        )
                        try:
                            proc.stdin.close()
                        except Exception:
                            pass
                        try:
                            proc.kill()
                        except Exception:
                            pass
                        continue

                    self._ffmpeg_format = profile.pixel_format
                    self._stream_width = profile.width
                    self._stream_height = profile.height
                    print(
                        f"[output] v4l2loopback ffmpeg started with pix_fmt={profile.pixel_format} "
                        f"size={profile.width}x{profile.height} mode={mode}",
                        flush=True,
                    )
                    return proc

        raise RuntimeError(
            f"ffmpeg initialization failed for v4l2 output device={device_path} "
            f"all candidate profiles failed. Last error: {last_error or 'unknown'}"
        )

    def write(self, frame: np.ndarray) -> None:
        if self._proc.stdin is None:
            raise RuntimeError("v4l2loopback ffmpeg stdin is not available.")

        normalized = frame
        if normalized.ndim == 2:
            normalized = cv2.cvtColor(normalized, cv2.COLOR_GRAY2BGR)
        elif normalized.ndim == 3 and normalized.shape[2] == 4:
            normalized = cv2.cvtColor(normalized, cv2.COLOR_BGRA2BGR)
        elif normalized.ndim != 3 or normalized.shape[2] != 3:
            raise RuntimeError(f"Unsupported frame shape for v4l2loopback output: {normalized.shape}")

        if normalized.dtype != np.uint8:
            normalized = np.clip(normalized, 0, 255).astype(np.uint8)

        if normalized.shape[1] != self._stream_width or normalized.shape[0] != self._stream_height:
            normalized = cv2.resize(
                normalized,
                (self._stream_width, self._stream_height),
                interpolation=cv2.INTER_LINEAR,
            )

        normalized = np.ascontiguousarray(normalized)
        try:
            self._proc.stdin.write(normalized.tobytes())
            self._frames_sent += 1
            if self._frames_sent == 1:
                print("[output] first frame sent to v4l2loopback device", flush=True)
                mean_brightness = float(normalized.mean())
                print(
                    f"[output] first frame stats: shape={normalized.shape} mean={mean_brightness:.2f} "
                    f"dtype={normalized.dtype}",
                    flush=True,
                )
            elif self._frames_sent % 120 == 0:
                print(f"[output] streaming ok: frames_sent={self._frames_sent}", flush=True)
        except BrokenPipeError as exc:
            stderr_detail = ""
            if self._proc.stderr is not None:
                try:
                    stderr_detail = self._proc.stderr.read1(1024).decode("utf-8", errors="ignore").strip()
                except Exception:
                    stderr_detail = ""
            if stderr_detail:
                print(f"[output] v4l2loopback ffmpeg stderr hint: {stderr_detail}", flush=True)
            raise RuntimeError(
                "ffmpeg pipe to v4l2loopback is broken. "
                "Check output device capability for the selected stream profile "
                f"({self._stream_width}x{self._stream_height}@{self._config.fps}, auto-selected pix_fmt='{self._ffmpeg_format}'). "
                "The pix_fmt is chosen automatically at startup and is not read from config. "
                "Adjust video device settings and retry."
            ) from exc

    def release(self) -> None:
        if self._proc.stdin is not None:
            try:
                self._proc.stdin.close()
            except Exception:
                pass
        try:
            self._proc.wait(timeout=2)
        except Exception:
            self._proc.kill()
