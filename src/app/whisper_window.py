#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import platform
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path


from src.app.rotating_log import install_rotating_stdout_log
from src.app.sentence_boundary import RegexSentenceBoundaryDetector, sentence_end_count as _boundary_sentence_end_count, split_completed_sentences as _boundary_split_completed_sentences
from src.app.translation_model import TranslationRequest, build_text_translator
from src.domain.whisper_defaults import whisper_default
from src.domain.config import AppConfig, WhisperConfig


SAMPLE_RATE = 16000
DEFAULT_CHUNK_SECONDS = float(whisper_default("chunkSeconds"))
DEFAULT_WINDOW_GEOMETRY = "780x420"
DEFAULT_WINDOW_GEOMETRY_META = {
    "whisperWindowGeometry": "780x420+50+119",
    "whisperTranslationWindowGeometry": "780x420+860+119",
}
MIN_WINDOW_WIDTH = 520
MIN_WINDOW_HEIGHT = 280
FINAL_TEXT_TAG = "final_text"
PARTIAL_TEXT_TAG = "partial_text"
FINAL_TEXT_COLOR = "black"
PARTIAL_TEXT_COLOR = "#008000"
MIN_SEGMENT_AVG_LOGPROB = -1.0
MAX_SEGMENT_NO_SPEECH_PROB = 0.75
RECENT_TRANSCRIPT_WINDOW = 8
MAX_RECENT_SHORT_TEXT_REPEATS = 2
MAX_PENDING_SENTENCE_CHUNKS = 10
MAX_PENDING_SENTENCE_CHARS = 180
SLOW_PENDING_SENTENCE_CHUNKS = 4
SLOW_PENDING_SENTENCE_CHARS = 45
SLOW_PENDING_MAX_CHARS_PER_CHUNK = 18.0
SENTENCE_CONFIRM_CHUNKS = 2
SENTENCE_CONFIRM_MAX_AGE_CHUNKS = 2
MIN_PROVISIONAL_TRANSLATION_WORDS = 6
PROVISIONAL_TRANSLATION_ENABLED = False
_SENTENCE_END_PATTERN = r"(?:(?<!\d)\.(?!\d)|[!?。！？…]+)"
_SENTENCE_END_RE = re.compile(rf"(.+?{_SENTENCE_END_PATTERN})(?=\s+|$)")
_SENTENCE_END_MARK_RE = re.compile(_SENTENCE_END_PATTERN)
_WINDOW_TITLES = {
    "en": {
        "transcript": "ai-virtual-cam Whisper Transcript",
        "translation": "ai-virtual-cam Whisper Translation",
    },
    "ko": {
        "transcript": "ai-virtual-cam 위스퍼 전사",
        "translation": "ai-virtual-cam 위스퍼 번역",
    },
}
_WINDOW_GEOMETRY_RE = re.compile(
    r"^(?P<width>\d+)x(?P<height>\d+)(?P<x_sign>[+-])(?P<x>\d+)(?P<y_sign>[+-])(?P<y>\d+)$"
)


@dataclass(frozen=True)
class TranscriptEvent:
    kind: str
    text: str
    display: bool = True
    log_text: str | None = None
    final: bool = True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show local Whisper transcript window.")
    parser.add_argument("--config", default="~/.avc/setting.json", help="Path to the JSON config file.")
    return parser.parse_args()


def _log_line(message: str, *, file=None) -> None:
    target = sys.stdout if file is None else file
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", file=target, flush=True)


def _load_ui_language(config_path: Path) -> str:
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        _log_line(f"[avc] whisper status: UI language load failed: {exc}")
        return "en"
    if not isinstance(raw, dict):
        return "en"
    meta = raw.get("meta") or {}
    if not isinstance(meta, dict):
        return "en"
    language = str(meta.get("language", "en")).strip().lower()
    return language if language in _WINDOW_TITLES else "en"


def _window_title(kind: str, language: str) -> str:
    titles = _WINDOW_TITLES.get(language) or _WINDOW_TITLES["en"]
    return titles.get(kind, _WINDOW_TITLES["en"].get(kind, "ai-virtual-cam"))


def _parse_window_geometry(geometry: object) -> dict[str, int] | None:
    if not isinstance(geometry, str):
        return None
    match = _WINDOW_GEOMETRY_RE.match(geometry.strip())
    if match is None:
        return None
    x = int(match.group("x"))
    y = int(match.group("y"))
    if match.group("x_sign") == "-":
        x = -x
    if match.group("y_sign") == "-":
        y = -y
    return {
        "width": int(match.group("width")),
        "height": int(match.group("height")),
        "x": x,
        "y": y,
    }


def _format_window_geometry(parts: dict[str, int]) -> str:
    x = int(parts["x"])
    y = int(parts["y"])
    return f'{int(parts["width"])}x{int(parts["height"])}{x:+d}{y:+d}'


def _window_restore_extent(root) -> tuple[int, int]:
    width = 0
    height = 0
    for width_name, height_name in (("winfo_vrootwidth", "winfo_vrootheight"), ("winfo_screenwidth", "winfo_screenheight")):
        try:
            width = max(width, int(getattr(root, width_name)()))
            height = max(height, int(getattr(root, height_name)()))
        except Exception:
            pass
    # Some X11/Tk setups report only the primary monitor before the window is mapped.
    # Allow the common two-monitor desktop extent so saved secondary-monitor windows reopen in place.
    if width > 0:
        width *= 2
    if height > 0:
        height *= 2
    return width, height


def _window_manager_geometry(window) -> str:
    try:
        geometry = window.geometry()
        if isinstance(geometry, str) and geometry.strip():
            return geometry
    except TypeError:
        pass
    except Exception:
        pass
    return window.winfo_geometry()


def _sanitize_window_geometry(geometry: object, screen_width: int, screen_height: int) -> str | None:
    parts = _parse_window_geometry(geometry)
    if parts is None:
        return None
    width = parts["width"]
    height = parts["height"]
    x = parts["x"]
    y = parts["y"]
    if width < MIN_WINDOW_WIDTH or height < MIN_WINDOW_HEIGHT:
        return None
    if screen_width <= 0 or screen_height <= 0:
        return _format_window_geometry(parts)
    visible_margin = 80
    if x >= screen_width - visible_margin or y >= screen_height - visible_margin:
        return None
    if x + width <= visible_margin or y + height <= visible_margin:
        return None
    return _format_window_geometry(parts)


def _load_window_geometry(config_path: Path, key: str, root) -> str | None:
    default_geometry = DEFAULT_WINDOW_GEOMETRY_META.get(key)
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            _log_line(
                f"[avc] whisper status: window geometry defaulted: key={key} "
                f"reason=invalid_config default={default_geometry}"
            )
            return default_geometry
        meta = raw.get("meta") or {}
        if not isinstance(meta, dict):
            _log_line(
                f"[avc] whisper status: window geometry defaulted: key={key} "
                f"reason=invalid_meta default={default_geometry}"
            )
            return default_geometry
        screen_width, screen_height = _window_restore_extent(root)
        saved = meta.get(key)
        restored = _sanitize_window_geometry(saved, screen_width, screen_height)
        if restored:
            _log_line(
                f"[avc] whisper status: window geometry restored: key={key} geometry={restored} "
                f"extent={screen_width}x{screen_height}"
            )
            return restored
        if default_geometry is not None:
            _log_line(
                f"[avc] whisper status: window geometry defaulted: key={key} "
                f"saved={saved!r} default={default_geometry} extent={screen_width}x{screen_height}"
            )
            return default_geometry
        _log_line(
            f"[avc] whisper status: window geometry restore skipped: key={key} "
            f"saved={saved!r} extent={screen_width}x{screen_height}"
        )
        return None
    except Exception as exc:
        _log_line(f"[avc] whisper status: window geometry load failed: {exc}")
        return default_geometry


def _save_window_geometry(
    config_path: Path,
    key: str,
    geometry: str,
    screen_width: int = 0,
    screen_height: int = 0,
) -> None:
    del config_path
    try:
        sanitized = _sanitize_window_geometry(geometry, screen_width, screen_height)
        if sanitized is None:
            _log_line(f"[avc] whisper status: window geometry cache skipped: key={key} invalid_geometry={geometry}")
            return
        _log_line(f"[avc] whisper status: window geometry cached: key={key} geometry={sanitized}")
    except Exception as exc:
        _log_line(f"[avc] whisper status: window geometry cache failed: key={key} error={exc}")

def _sounddevice_device_name(configured: str) -> str | None:
    value = str(configured).strip()
    if not value or value.lower() == "default":
        return None
    return value


def _is_exact_pulse_source(configured: str) -> bool:
    if platform.system() != "Linux":
        return False
    value = str(configured).strip().lower()
    if not value or value == "default":
        return False
    return value.startswith("alsa_input.") or value.endswith(".monitor") or value == "ai-virtual-cam"


def _is_modal_output_event(event: TranscriptEvent) -> bool:
    return event.display and event.kind in {"transcript", "translation"}


def _normalized_text(text: str) -> str:
    return " ".join(str(text).split())


def _text_units(text: str) -> tuple[list[str], str]:
    normalized = _normalized_text(text)
    if not normalized:
        return [], " "
    if " " in normalized:
        return normalized.split(), " "
    return list(normalized), ""


def _join_text_units(units: list[str], separator: str) -> str:
    return separator.join(units).strip()


def _stable_window_text(text: str, commit_lag_seconds: float, window_seconds: float) -> str:
    normalized = _normalized_text(text)
    if not normalized or commit_lag_seconds <= 0.0:
        return normalized
    units, separator = _text_units(normalized)
    if len(units) <= 1:
        return ""
    ratio = min(max(commit_lag_seconds / max(window_seconds, 0.001), 0.0), 0.95)
    hold_count = max(1, int(len(units) * ratio + 0.999))
    stable_units = units[: max(0, len(units) - hold_count)]
    return _join_text_units(stable_units, separator)


def _new_text_delta(committed_text: str, stable_text: str) -> str:
    committed = _normalized_text(committed_text)
    stable = _normalized_text(stable_text)
    if not stable:
        return ""
    if not committed:
        return stable
    if committed.endswith(stable):
        return ""
    committed_units, committed_separator = _text_units(committed)
    stable_units, stable_separator = _text_units(stable)
    if committed_separator != stable_separator:
        committed_units, stable_units = list(committed), list(stable)
        stable_separator = ""
    max_overlap = min(len(committed_units), len(stable_units))
    for overlap in range(max_overlap, 0, -1):
        if committed_units[-overlap:] == stable_units[:overlap]:
            return _join_text_units(stable_units[overlap:], stable_separator)
    if stable in committed:
        return ""
    internal_delta = _new_text_delta_after_internal_overlap(committed, stable)
    if internal_delta is not None:
        return internal_delta
    return stable


def _word_units(text: str) -> list[str]:
    return re.findall(r"[0-9A-Za-z가-힣]+", _normalized_text(text).lower())


def _new_text_delta_after_internal_overlap(committed_text: str, stable_text: str) -> str | None:
    committed_words = _word_units(committed_text)
    stable_units, stable_separator = _text_units(stable_text)
    if stable_separator != " ":
        return None
    stable_word_pairs: list[tuple[str, int]] = []
    for unit_index, unit in enumerate(stable_units):
        for word in _word_units(unit):
            stable_word_pairs.append((word, unit_index))
    stable_words = [word for word, _unit_index in stable_word_pairs]
    if len(committed_words) < 4 or len(stable_words) < 4:
        return None

    best_j = 0
    best_len = 0
    for i in range(len(committed_words)):
        for j in range(len(stable_words)):
            length = 0
            while (
                i + length < len(committed_words)
                and j + length < len(stable_words)
                and committed_words[i + length] == stable_words[j + length]
            ):
                length += 1
            if length > best_len:
                best_j = j
                best_len = length
    if best_len < 4:
        return None
    if best_len / max(len(stable_words), 1) >= 0.85:
        return ""
    suffix_word_index = best_j + best_len
    if suffix_word_index >= len(stable_word_pairs):
        return ""
    suffix_unit_index = stable_word_pairs[suffix_word_index][1]
    suffix = _join_text_units(stable_units[suffix_unit_index:], stable_separator)
    return suffix or ""


def _phrase_key(units: list[str]) -> list[str]:
    return _word_units(" ".join(units))


def _repeated_phrase_key_matches(left_key: list[str], right_key: list[str]) -> bool:
    if left_key == right_key:
        return True
    return len(left_key) >= 4 and len(left_key) == len(right_key) and left_key[1:] == right_key[1:]


def _collapse_near_repeated_phrases(units: list[str]) -> bool:
    for phrase_len in range(min(12, len(units) // 2), 3, -1):
        for left_start in range(0, len(units) - phrase_len):
            left_key = _phrase_key(units[left_start : left_start + phrase_len])
            if not left_key:
                continue
            max_right_start = min(len(units) - phrase_len, left_start + phrase_len + 8)
            for right_start in range(left_start + phrase_len, max_right_start + 1):
                right_key = _phrase_key(units[right_start : right_start + phrase_len])
                if _repeated_phrase_key_matches(left_key, right_key):
                    delete_len = phrase_len
                    while (
                        left_start + delete_len < right_start
                        and right_start + delete_len < len(units)
                        and _phrase_key([units[left_start + delete_len]]) == _phrase_key([units[right_start + delete_len]])
                    ):
                        delete_len += 1
                    del units[right_start : right_start + delete_len]
                    return True
    return False


def _collapse_adjacent_repeated_prefix_units(units: list[str]) -> bool:
    for index in range(1, len(units)):
        previous_key = _phrase_key([units[index - 1]])
        current_key = _phrase_key([units[index]])
        if "-" in units[index] and len(previous_key) == 1 and len(current_key) >= 2 and previous_key[0] == current_key[0]:
            del units[index - 1]
            return True
    return False


def _collapse_adjacent_repeated_phrases(text: str) -> str:
    normalized = _normalized_text(text)
    units, separator = _text_units(normalized)
    if separator == "" or len(units) < 6:
        return normalized
    while _collapse_adjacent_repeated_prefix_units(units):
        pass
    passes = 0
    changed = True
    while changed and passes < 4:
        passes += 1
        changed = False
        index = 0
        while index < len(units):
            collapsed = False
            max_phrase_len = min(16, (len(units) - index) // 2)
            for phrase_len in range(max_phrase_len, 2, -1):
                left = units[index : index + phrase_len]
                right = units[index + phrase_len : index + (phrase_len * 2)]
                if _phrase_key(left) and _phrase_key(left) == _phrase_key(right):
                    del units[index + phrase_len : index + (phrase_len * 2)]
                    changed = True
                    collapsed = True
                    break
            if not collapsed:
                index += 1
        if _collapse_near_repeated_phrases(units):
            changed = True
    return _join_text_units(units, separator)


def _is_subsequence_at(words: list[str], candidate: list[str], start: int) -> bool:
    return words[start : start + len(candidate)] == candidate


def _collapse_adjacent_words(words: list[str]) -> list[str]:
    collapsed: list[str] = []
    for word in words:
        if collapsed and collapsed[-1] == word:
            continue
        collapsed.append(word)
    return collapsed


def _duplicate_key_words(words: list[str]) -> list[str]:
    key_words = _collapse_adjacent_words(words)
    while len(key_words) >= 3 and key_words[:2] in (["not", "just"], ["no", "not"]):
        key_words = key_words[2:]
    return key_words


def _contains_word_sequence(words: list[str], candidate: list[str]) -> bool:
    if not candidate or len(candidate) > len(words):
        return False
    for start in range(0, len(words) - len(candidate) + 1):
        if _is_subsequence_at(words, candidate, start):
            return True
    return False


def _longest_prefix_run_in_words(words: list[str], candidate: list[str]) -> int:
    best = 0
    for start in range(len(words)):
        length = 0
        while start + length < len(words) and length < len(candidate) and words[start + length] == candidate[length]:
            length += 1
        best = max(best, length)
    return best


def _longest_suffix_run_in_words(words: list[str], candidate: list[str]) -> int:
    best = 0
    for end in range(len(words), 0, -1):
        length = 0
        while end - 1 - length >= 0 and len(candidate) - 1 - length >= 0 and words[end - 1 - length] == candidate[len(candidate) - 1 - length]:
            length += 1
        best = max(best, length)
    return best


def _prefix_words_match(left: str, right: str) -> bool:
    if left == right:
        return True
    return {left, right} <= {"a", "an", "the"}


def _longest_prefix_revision_run(left_words: list[str], right_words: list[str]) -> int:
    length = 0
    while length < len(left_words) and length < len(right_words):
        if not _prefix_words_match(left_words[length], right_words[length]):
            break
        length += 1
    return length


def _trim_leading_boundary_noise(text: str) -> str:
    words = _word_units(text)
    if len(words) >= 4 and words[:4] == ["if", "you", "when", "you"]:
        return " ".join(words[2:]).strip()
    if len(words) >= 3 and words[:3] == ["you", "when", "you"]:
        return " ".join(words[1:]).strip()
    return text.strip()


def _sentence_delta_from_words(words: list[str]) -> str:
    return _trim_leading_boundary_noise(" ".join(words).strip())


def _sentence_output_delta(committed_text: str, sentence: str) -> str:
    normalized = _collapse_adjacent_repeated_phrases(_normalized_text(sentence))
    if not normalized:
        return ""
    committed_words = _word_units(committed_text)
    sentence_words = _word_units(normalized)
    if not committed_words or not sentence_words:
        return normalized
    if len(sentence_words) <= len(committed_words):
        for start in range(0, len(committed_words) - len(sentence_words) + 1):
            if _is_subsequence_at(committed_words, sentence_words, start):
                return ""

    if 1 <= len(committed_words) <= 4:
        for start in range(0, len(sentence_words) - len(committed_words) + 1):
            if _is_subsequence_at(sentence_words, committed_words, start):
                suffix_words = sentence_words[start + len(committed_words) :]
                if len(suffix_words) >= 3:
                    return _sentence_delta_from_words(suffix_words)

    committed_key_words = _duplicate_key_words(committed_words)
    sentence_key_words = _duplicate_key_words(sentence_words)
    if len(sentence_key_words) >= 5 and (
        _contains_word_sequence(committed_key_words, sentence_key_words)
        or _contains_word_sequence(sentence_key_words, committed_key_words)
    ):
        length_ratio = min(len(committed_key_words), len(sentence_key_words)) / max(len(committed_key_words), len(sentence_key_words), 1)
        if length_ratio >= 0.9:
            return ""

    prefix_len = max(
        _longest_prefix_run_in_words(committed_words, sentence_words),
        _longest_prefix_revision_run(committed_words, sentence_words),
    )
    suffix_len = _longest_suffix_run_in_words(committed_words, sentence_words)
    if prefix_len >= 3 or suffix_len >= 3:
        start = prefix_len if prefix_len >= 3 else 0
        end = len(sentence_words) - suffix_len if suffix_len >= 3 else len(sentence_words)
        if start >= end:
            return ""
        middle_words = sentence_words[start:end]
        if prefix_len >= 5 and len(committed_words) <= 10:
            return _sentence_delta_from_words(middle_words)
        if len(middle_words) <= max(2, len(sentence_words) // 2):
            return _sentence_delta_from_words(middle_words)

    best_i = 0
    best_j = 0
    best_len = 0
    for i in range(len(committed_words)):
        for j in range(len(sentence_words)):
            length = 0
            while (
                i + length < len(committed_words)
                and j + length < len(sentence_words)
                and committed_words[i + length] == sentence_words[j + length]
            ):
                length += 1
            if length > best_len:
                best_i = i
                best_j = j
                best_len = length
    coverage = best_len / max(len(sentence_words), 1)
    if coverage >= 0.85:
        return ""
    if best_j == 0 and best_len >= 4:
        suffix_words = sentence_words[best_len:]
        if len(suffix_words) >= 3:
            return _sentence_delta_from_words(suffix_words)
        return ""
    if best_i + best_len == len(committed_words) and 0 < best_j <= 3 and best_len >= 8:
        suffix_words = sentence_words[best_j + best_len :]
        if len(suffix_words) >= 3:
            return _sentence_delta_from_words(suffix_words)
        return ""
    if best_i + best_len == len(committed_words) and best_j == 1 and best_len >= 4:
        suffix_words = sentence_words[best_j + best_len :]
        if len(suffix_words) >= 3:
            return _sentence_delta_from_words(suffix_words)
        return ""
    if best_i + best_len == len(committed_words) and best_j == 0 and best_len >= 2:
        suffix_words = sentence_words[best_len:]
        if best_len >= 3 or len(suffix_words) >= 5:
            return _sentence_delta_from_words(suffix_words)
    return normalized


def _best_common_word_run(a_words: list[str], b_words: list[str]) -> tuple[int, int, int]:
    best_i = 0
    best_j = 0
    best_len = 0
    for i in range(len(a_words)):
        for j in range(len(b_words)):
            length = 0
            while i + length < len(a_words) and j + length < len(b_words) and a_words[i + length] == b_words[j + length]:
                length += 1
            if length > best_len:
                best_i = i
                best_j = j
                best_len = length
    return best_i, best_j, best_len


def _common_word_run(a_words: list[str], b_words: list[str]) -> int:
    _best_i, _best_j, best_len = _best_common_word_run(a_words, b_words)
    return best_len


def _sentences_are_revisions(left: str, right: str) -> bool:
    left_words = _word_units(left)
    right_words = _word_units(right)
    if not left_words or not right_words:
        return False
    if left_words == right_words:
        return True
    if 1 <= len(left_words) <= 4 and len(right_words) > len(left_words):
        if all(_prefix_words_match(left_word, right_word) for left_word, right_word in zip(left_words, right_words)):
            return True
    shorter = min(len(left_words), len(right_words))
    best_i, best_j, common_run = _best_common_word_run(left_words, right_words)
    prefix_run = _longest_prefix_revision_run(left_words, right_words)
    if common_run >= 8 and best_i + common_run == len(left_words) and best_j <= 3:
        return True
    if prefix_run >= 5 and common_run >= 5 and len(right_words) >= len(left_words):
        return True
    return common_run >= 4 and common_run / max(shorter, 1) >= 0.6


def _should_translate_staged_sentence(staged_sentence: str, staged_confirmations: int) -> bool:
    if not PROVISIONAL_TRANSLATION_ENABLED:
        return False
    if staged_confirmations >= SENTENCE_CONFIRM_CHUNKS:
        return True
    return len(_word_units(staged_sentence)) >= MIN_PROVISIONAL_TRANSLATION_WORDS


def _should_age_staged_sentence(staged_sentence: str, pending_text: str) -> bool:
    if not staged_sentence:
        return False
    if pending_text and _sentences_are_revisions(staged_sentence, pending_text):
        return False
    return True


def _prefer_sentence_revision(left: str, right: str) -> str:
    left_words = _word_units(left)
    right_words = _word_units(right)
    if len(right_words) > len(left_words):
        return _normalized_text(right)
    if _sentence_end_count(right) > _sentence_end_count(left):
        return _normalized_text(right)
    return _normalized_text(left)


def _append_committed_text(committed_text: str, new_text: str) -> str:
    combined = _normalized_text(f"{committed_text} {new_text}")
    if len(combined) <= 4000:
        return combined
    return combined[-4000:]


def _pending_new_text_combined(pending_text: str, new_text: str) -> str:
    from src.app.sentence_boundary import pending_new_text_combined

    return pending_new_text_combined(pending_text, new_text)


def _split_completed_sentences(pending_text: str, new_text: str) -> tuple[list[str], str]:
    return _boundary_split_completed_sentences(pending_text, new_text)


def _sentence_end_count(text: str) -> int:
    return _boundary_sentence_end_count(text)


_INCOMPLETE_TAIL_WORDS = {
    "a",
    "an",
    "and",
    "at",
    "because",
    "but",
    "can",
    "for",
    "from",
    "if",
    "in",
    "it",
    "of",
    "on",
    "or",
    "re",
    "that",
    "the",
    "to",
    "which",
    "with",
}


def _has_incomplete_sentence_tail(text: str) -> bool:
    words = _word_units(text)
    if not words:
        return False
    if words[-1] in _INCOMPLETE_TAIL_WORDS:
        return True
    if len(words) >= 2 and words[-1].isdigit() and words[-2] in {"from", "to"}:
        return True
    return False


def _forced_sentence_reason(pending_text: str, pending_chunks: int) -> str:
    normalized = _normalized_text(pending_text)
    if not normalized:
        return ""
    pending_chars = len(normalized)
    chars_per_chunk = pending_chars / max(pending_chunks, 1)
    if pending_chunks >= MAX_PENDING_SENTENCE_CHUNKS and not _has_incomplete_sentence_tail(normalized):
        return "pending_chunks"
    if pending_chars >= MAX_PENDING_SENTENCE_CHARS and _sentence_end_count(normalized) > 0:
        return "pending_chars"
    if (
        pending_chunks >= SLOW_PENDING_SENTENCE_CHUNKS
        and pending_chars >= SLOW_PENDING_SENTENCE_CHARS
        and chars_per_chunk <= SLOW_PENDING_MAX_CHARS_PER_CHUNK
        and not _has_incomplete_sentence_tail(normalized)
    ):
        return "slow_pending"
    return ""


def _diagnostic_tail(text: str, limit: int = 90) -> str:
    normalized = _normalized_text(text)
    if len(normalized) > limit:
        normalized = "..." + normalized[-limit:]
    return repr(normalized)


class WhisperTranscriptWorker:
    def __init__(self, config: WhisperConfig, events: queue.Queue[TranscriptEvent]) -> None:
        self._cfg = config
        self._events = events
        self._stop = threading.Event()
        self._audio_queue: queue.Queue[object] = queue.Queue(maxsize=120)
        self._capture_process: subprocess.Popen[bytes] | None = None
        self._capture_thread: threading.Thread | None = None
        self._recent_transcripts: deque[str] = deque(maxlen=RECENT_TRANSCRIPT_WINDOW)
        self._sentence_boundary_detector = RegexSentenceBoundaryDetector()

    def _emit(
        self,
        kind: str,
        text: str,
        *,
        display: bool = True,
        log_text: str | None = None,
        final: bool = True,
    ) -> None:
        _log_line(f"[avc] whisper {kind}: {log_text if log_text is not None else text}")
        self._events.put(TranscriptEvent(kind, text, display, log_text, final))

    def _accepted_segment_texts(self, segments) -> tuple[list[str], list[str]]:
        texts: list[str] = []
        rejected: list[str] = []
        for segment in segments:
            text = segment.text.strip()
            if not text:
                continue
            avg_logprob = float(getattr(segment, "avg_logprob", 0.0) or 0.0)
            no_speech_prob = float(getattr(segment, "no_speech_prob", 0.0) or 0.0)
            if no_speech_prob >= MAX_SEGMENT_NO_SPEECH_PROB:
                rejected.append(f"no_speech text={text!r} prob={no_speech_prob:.2f}")
                continue
            if avg_logprob <= MIN_SEGMENT_AVG_LOGPROB:
                rejected.append(f"low_logprob text={text!r} avg_logprob={avg_logprob:.2f}")
                continue
            texts.append(text)
        return texts, rejected

    def _is_repeated_hallucination(self, text: str) -> bool:
        normalized = " ".join(text.split())
        if not normalized:
            return False
        repeats = sum(1 for item in self._recent_transcripts if item == normalized)
        return len(normalized) <= 24 and repeats >= MAX_RECENT_SHORT_TEXT_REPEATS

    def _remember_transcript(self, text: str) -> None:
        normalized = " ".join(text.split())
        if normalized:
            self._recent_transcripts.append(normalized)

    def stop(self) -> None:
        self._stop.set()
        process = self._capture_process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=1.0)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass

    def run(self) -> None:
        try:
            if self._cfg.backend == "mock":
                self._run_mock()
                return
            if self._cfg.backend != "faster-whisper":
                raise RuntimeError(
                    "지원하지 않는 whisper.backend입니다: "
                    f"{self._cfg.backend}. 현재 창 출력은 faster-whisper 또는 mock만 지원합니다."
                )

            try:
                import numpy as np
            except ModuleNotFoundError as exc:
                raise RuntimeError("numpy 모듈이 없습니다. ./bin/avc setup 실행 후 재시도하세요.") from exc
            sd = None
            if not _is_exact_pulse_source(self._cfg.inputDevice):
                try:
                    import sounddevice as sd
                except ModuleNotFoundError as exc:
                    raise RuntimeError("sounddevice 모듈이 없습니다. ./bin/avc setup 실행 후 재시도하세요.") from exc
            try:
                from faster_whisper import WhisperModel
            except ModuleNotFoundError as exc:
                raise RuntimeError(
                    "faster-whisper 모듈이 없습니다. 로컬 Whisper를 사용하려면 faster-whisper와 CUDA 런타임을 설치하세요."
                ) from exc

            self._emit(
                "status",
                "Whisper 모델 로딩 중: "
                f"backend={self._cfg.backend} model={self._cfg.model} "
                f"device={self._cfg.device} compute={self._cfg.computeType}. "
                "최초 실행이면 모델 다운로드 때문에 시간이 걸릴 수 있습니다.",
            )
            try:
                model = WhisperModel(
                    self._cfg.model,
                    device=self._cfg.device,
                    compute_type=self._cfg.computeType,
                )
            except Exception as exc:
                raise RuntimeError(
                    "Whisper 모델 로딩 실패: "
                    f"backend={self._cfg.backend} model={self._cfg.model} "
                    f"device={self._cfg.device} computeType={self._cfg.computeType}. "
                    "float16 오류가 발생하면 config의 Whisper 장치를 cuda로 명시하고 CUDA 런타임을 확인하거나, "
                    "CPU 실행 시 computeType을 int8 또는 float32로 변경하세요. "
                    f"원인: {exc}"
                ) from exc
            self._emit("status", "Whisper 모델 로딩 완료")
            text_translator = None
            if self._cfg.translationEnabled:
                translation_status = (
                    "Whisper 내장 영어 번역 창 사용"
                    if self._cfg.translationBackend == "whisper"
                    else "외부 텍스트 번역 창 사용"
                )
                self._emit(
                    "status",
                    f"{translation_status}: "
                    f"backend={self._cfg.translationBackend} target_language={self._cfg.translationTargetLanguage} "
                    f"model={self._cfg.translationModel} device={self._cfg.translationDevice} "
                    f"compute={self._cfg.translationComputeType} translation_beam={self._cfg.translationBeamSize} "
                    f"translation_max_tokens={self._cfg.translationMaxNewTokens}",
                )
                text_translator = build_text_translator(
                    self._cfg.translationBackend,
                    self._cfg.translationModel,
                    self._cfg.translationDevice,
                    self._cfg.translationComputeType,
                    self._cfg.translationBeamSize,
                    self._cfg.translationMaxNewTokens,
                )
            self._emit("status", f"입력 장치 열기: {self._cfg.inputDevice}")

            if _is_exact_pulse_source(self._cfg.inputDevice):
                self._start_pulse_capture(np)
                self._emit("status", f"Pulse source 직접 캡처 시작: {self._cfg.inputDevice}")
                self._transcribe_loop(model, np, text_translator)
                return

            assert sd is not None

            def callback(indata, frames, time_info, status) -> None:
                if status:
                    self._emit("status", f"오디오 입력 상태: {status}")
                mono = np.asarray(indata, dtype=np.float32)
                if mono.ndim == 2:
                    mono = mono[:, 0]
                try:
                    self._audio_queue.put_nowait(mono.copy())
                except queue.Full:
                    self._emit("status", "Whisper 입력 버퍼가 가득 차 오디오 프레임을 건너뜁니다.")

            device = _sounddevice_device_name(self._cfg.inputDevice)
            self._emit("status", f"sounddevice 캡처 시작: runtime_device={device or 'default'}")
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                device=device,
                callback=callback,
            ):
                self._emit("status", "Whisper 전사 시작")
                self._transcribe_loop(model, np, text_translator)
        except Exception as exc:
            self._emit("error", str(exc))

    def _start_pulse_capture(self, np) -> None:
        recorder = shutil.which("parec") or shutil.which("parecord")
        if recorder is None:
            raise RuntimeError("parec/parecord command not found. Run ./bin/avc setup and try again.")
        cmd = [
            recorder,
            "--device",
            self._cfg.inputDevice,
            "--format=s16le",
            "--rate",
            str(SAMPLE_RATE),
            "--channels",
            "1",
            "--raw",
        ]
        self._emit("status", "Pulse recorder spawn: " + " ".join(cmd))
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self._capture_process = process
        bytes_per_block = int(SAMPLE_RATE * 0.2) * 2

        def read_loop() -> None:
            assert process.stdout is not None
            self._emit("status", f"Pulse recorder reader started: pid={process.pid}")
            while not self._stop.is_set() and process.poll() is None:
                data = process.stdout.read(bytes_per_block)
                if not data:
                    break
                try:
                    samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                    self._audio_queue.put(samples, timeout=0.2)
                except queue.Full:
                    self._emit("status", "Whisper 입력 버퍼가 가득 차 Pulse 프레임을 건너뜁니다.")
                except Exception as exc:
                    self._emit("error", f"Pulse 캡처 처리 실패: {exc}")
                    break
            if process.poll() not in (None, 0) and not self._stop.is_set():
                stderr = ""
                try:
                    stderr = (process.stderr.read() if process.stderr is not None else b"").decode(errors="replace").strip()
                except Exception:
                    stderr = ""
                self._emit("error", stderr or f"Pulse recorder exited with code {process.returncode}")
            else:
                self._emit("status", f"Pulse recorder reader stopped: pid={process.pid} code={process.poll()}")

        self._capture_thread = threading.Thread(target=read_loop, daemon=True)
        self._capture_thread.start()

    def _transcribe_loop(self, model, np, text_translator=None) -> None:
        audio_blocks: deque[object] = deque()
        buffered = 0
        pending_step = 0
        step_seconds = float(self._cfg.stepSeconds)
        window_seconds = float(self._cfg.windowSeconds)
        commit_lag_seconds = float(self._cfg.commitLagSeconds)
        step_samples = int(SAMPLE_RATE * step_seconds)
        window_samples = int(SAMPLE_RATE * window_seconds)
        language = None if self._cfg.language == "auto" else self._cfg.language
        chunks = 0
        translation_failed = False
        committed_text = ""
        committed_translation_text = ""
        pending_transcript_text = ""
        pending_chunks = 0
        staged_sentence = ""
        staged_confirmations = 0
        staged_age = 0
        staged_translation_pending = False
        self._emit(
            "status",
            f"Whisper 전사 루프 시작: step_seconds={step_seconds} window_seconds={window_seconds} "
            f"commit_lag_seconds={commit_lag_seconds} language={self._cfg.language} "
            f"translation_enabled={self._cfg.translationEnabled} "
            f"translation_backend={self._cfg.translationBackend} "
            f"translation_target={self._cfg.translationTargetLanguage} beam_size={self._cfg.beamSize} "
            f"max_new_tokens={self._cfg.maxNewTokens} temperature={self._cfg.temperature} "
            f"without_timestamps=True translation_beam_size={self._cfg.translationBeamSize} "
            f"translation_max_new_tokens={self._cfg.translationMaxNewTokens}",
        )

        def trim_audio_window() -> None:
            nonlocal buffered
            while buffered > window_samples and audio_blocks:
                excess = buffered - window_samples
                oldest = audio_blocks[0]
                oldest_len = int(oldest.shape[0])
                if oldest_len <= excess:
                    audio_blocks.popleft()
                    buffered -= oldest_len
                    continue
                audio_blocks[0] = oldest[excess:]
                buffered -= excess
                break

        def finalize_staged_sentence(detected: str, reason: str) -> list[str]:
            nonlocal committed_text, staged_sentence, staged_confirmations, staged_age
            if not staged_sentence:
                return []
            output_sentence = _sentence_output_delta(committed_text, staged_sentence)
            staged_before = staged_sentence
            staged_sentence = ""
            staged_confirmations = 0
            staged_age = 0
            if not output_sentence:
                self._emit(
                    "status",
                    f"Whisper 확정 후보 중복 무시: chunk={chunks} reason={reason} text={staged_before!r}",
                    display=False,
                )
                return []
            committed_text = _append_committed_text(committed_text, output_sentence)
            self._remember_transcript(output_sentence)
            self._emit(
                "status",
                f"Whisper 문장 확정: chunk={chunks} reason={reason} text={output_sentence!r}",
                display=False,
            )
            self._emit("transcript", output_sentence, log_text=f"[{detected}] {output_sentence}", final=True)
            return [output_sentence]

        def stage_completed_sentence(sentence: str, detected: str) -> list[str]:
            nonlocal staged_sentence, staged_confirmations, staged_age, staged_translation_pending
            candidate = _sentence_output_delta(committed_text, sentence)
            if not candidate:
                self._emit("status", f"Whisper 중복 문장 무시: chunk={chunks} text={sentence!r}", display=False)
                return []
            if not staged_sentence:
                staged_sentence = candidate
                staged_confirmations = 1
                staged_age = 0
                staged_translation_pending = True
                self._emit("transcript", staged_sentence, log_text=f"[{detected}] {staged_sentence}", final=False)
                return []
            if _sentences_are_revisions(staged_sentence, candidate):
                staged_sentence = _prefer_sentence_revision(staged_sentence, candidate)
                staged_confirmations += 1
                staged_age = 0
                if staged_confirmations >= SENTENCE_CONFIRM_CHUNKS:
                    return finalize_staged_sentence(detected, "confirmed")
                staged_translation_pending = True
                self._emit("transcript", staged_sentence, log_text=f"[{detected}] {staged_sentence}", final=False)
                return []
            finalized = finalize_staged_sentence(detected, "replaced")
            staged_sentence = candidate
            staged_confirmations = 1
            staged_age = 0
            staged_translation_pending = True
            self._emit("transcript", staged_sentence, log_text=f"[{detected}] {staged_sentence}", final=False)
            return finalized

        def age_staged_sentence(detected: str, pending_text: str = "") -> list[str]:
            nonlocal staged_age
            if not staged_sentence:
                return []
            if not _should_age_staged_sentence(staged_sentence, pending_text):
                staged_age = 0
                self._emit(
                    "status",
                    f"Whisper staged aging 보류: chunk={chunks} staged={staged_sentence!r} pending={pending_text!r}",
                    display=False,
                )
                return []
            staged_age += 1
            if staged_age >= SENTENCE_CONFIRM_MAX_AGE_CHUNKS:
                return finalize_staged_sentence(detected, "aged")
            return []

        while not self._stop.is_set():
            try:
                block = self._audio_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            audio_blocks.append(block)
            block_len = int(block.shape[0])
            buffered += block_len
            pending_step += block_len
            trim_audio_window()
            if buffered < window_samples or pending_step < step_samples:
                continue
            pending_step = 0

            chunks += 1
            self._emit("status", f"Whisper 전사 요청: chunk={chunks} samples={buffered}", display=False)
            audio = np.concatenate(list(audio_blocks)).astype(np.float32, copy=False)
            chunk_audio_seconds = float(audio.shape[0]) / float(SAMPLE_RATE)
            chunk_started_at = time.perf_counter()
            translation_elapsed = 0.0
            translation_attempted = False
            translation_started_at = chunk_started_at
            text = ""
            staged_translation_pending = False
            try:
                stt_started_at = time.perf_counter()
                segments, info = model.transcribe(
                    audio,
                    language=language,
                    task="transcribe",
                    beam_size=self._cfg.beamSize,
                    temperature=self._cfg.temperature,
                    max_new_tokens=self._cfg.maxNewTokens,
                    without_timestamps=True,
                    condition_on_previous_text=False,
                )
                segment_list = list(segments)
                accepted_texts, rejected_reasons = self._accepted_segment_texts(segment_list)
                raw_window_text = " ".join(accepted_texts).strip()
                window_text = _collapse_adjacent_repeated_phrases(raw_window_text)
                repeat_collapse_chars = max(0, len(_normalized_text(raw_window_text)) - len(_normalized_text(window_text)))
                stable_text = _stable_window_text(window_text, commit_lag_seconds, window_seconds)
                delta_base_text = _append_committed_text(committed_text, pending_transcript_text)
                text = _new_text_delta(delta_base_text, stable_text)
                stt_elapsed = time.perf_counter() - stt_started_at
                detected = getattr(info, "language", self._cfg.language)
                if rejected_reasons:
                    self._emit(
                        "status",
                        f"Whisper 전사 후보 무시: chunk={chunks} reasons={'; '.join(rejected_reasons)}",
                        display=False,
                    )
                completed_sentences: list[str] = []
                final_sentences: list[str] = []
                forced_by = ""
                boundary_complete = 0
                boundary_soft = 0
                if text and self._is_repeated_hallucination(text):
                    self._emit("status", f"Whisper 반복 전사 무시: chunk={chunks} text={text!r}", display=False)
                    text = ""
                if text:
                    boundary_result = self._sentence_boundary_detector.split(pending_transcript_text, text, detected)
                    completed_sentences = boundary_result.completed
                    pending_transcript_text = boundary_result.pending
                    boundary_complete = boundary_result.boundary_count
                    boundary_soft = boundary_result.soft_boundary_count
                    if completed_sentences:
                        pending_chunks = 0
                    elif pending_transcript_text:
                        pending_chunks += 1
                        forced_by = _forced_sentence_reason(pending_transcript_text, pending_chunks)
                        if forced_by:
                            completed_sentences = [pending_transcript_text]
                            pending_transcript_text = ""
                            pending_chunks = 0
                    for sentence in completed_sentences:
                        final_sentences.extend(stage_completed_sentence(sentence, detected))
                    if pending_transcript_text:
                        self._emit(
                            "transcript",
                            pending_transcript_text,
                            log_text=f"[{detected}] {pending_transcript_text}",
                            final=False,
                        )
                    elif not completed_sentences:
                        final_sentences.extend(age_staged_sentence(detected, pending_transcript_text))
                else:
                    preview_chars = max(0, len(_normalized_text(window_text)) - len(_normalized_text(stable_text)))
                    self._emit(
                        "status",
                        f"Whisper 전사 결과 없음: chunk={chunks} preview_chars={preview_chars}",
                        display=False,
                    )
                    if pending_transcript_text:
                        pending_chunks += 1
                        forced_by = _forced_sentence_reason(pending_transcript_text, pending_chunks)
                        if forced_by:
                            completed_sentences = [pending_transcript_text]
                            pending_transcript_text = ""
                            pending_chunks = 0
                            for sentence in completed_sentences:
                                final_sentences.extend(stage_completed_sentence(sentence, detected))
                        else:
                            final_sentences.extend(age_staged_sentence(detected, pending_transcript_text))
                    else:
                        final_sentences.extend(age_staged_sentence(detected, pending_transcript_text))
                self._emit(
                    "status",
                    "Whisper 문장 진단: "
                    f"chunk={chunks} completed={len(completed_sentences)} final={len(final_sentences)} forced_by={forced_by or 'none'} "
                    f"boundary_backend={self._sentence_boundary_detector.backend} "
                    f"boundary_complete={boundary_complete} boundary_soft={boundary_soft} "
                    f"pending_chars={len(pending_transcript_text)} pending_chunks={pending_chunks} "
                    f"pending_chars_per_chunk={len(pending_transcript_text) / max(pending_chunks, 1):.1f} "
                    f"window_chars={len(_normalized_text(window_text))} stable_chars={len(_normalized_text(stable_text))} "
                    f"repeat_collapse_chars={repeat_collapse_chars} "
                    f"delta_chars={len(_normalized_text(text))} "
                    f"end_marks_window={_sentence_end_count(window_text)} end_marks_stable={_sentence_end_count(stable_text)} "
                    f"end_marks_delta={_sentence_end_count(text)} "
                    f"stable_tail={_diagnostic_tail(stable_text)} delta_tail={_diagnostic_tail(text)} "
                    f"pending_tail={_diagnostic_tail(pending_transcript_text)} "
                    f"staged_confirmations={staged_confirmations} staged_age={staged_age} "
                    f"staged_tail={_diagnostic_tail(staged_sentence)}",
                    display=False,
                )
                translation_jobs: list[tuple[str, bool]] = []
                if (
                    text_translator is not None
                    and staged_translation_pending
                    and staged_sentence
                    and _should_translate_staged_sentence(staged_sentence, staged_confirmations)
                ):
                    translation_jobs.append((staged_sentence, False))
                translation_jobs.extend((sentence, True) for sentence in final_sentences)
                if self._cfg.translationEnabled and not translation_failed and translation_jobs:
                    try:
                        translation_attempted = True
                        request_label = "Whisper 내장 번역 요청" if text_translator is None else "외부 텍스트 번역 요청"
                        target_language = self._cfg.translationTargetLanguage
                        source_language = detected if detected in {"ko", "en", "zh"} else self._cfg.language
                        for sentence, is_final_translation in translation_jobs:
                            if text_translator is None and not is_final_translation:
                                continue
                            translation_started_at = time.perf_counter()
                            self._emit("status", f"{request_label}: chunk={chunks} final={is_final_translation}", display=False)
                            translated_text = ""
                            if text_translator is None:
                                translated_segments, _translated_info = model.transcribe(
                                    audio,
                                    language=language,
                                    task="translate",
                                                    beam_size=self._cfg.beamSize,
                                    temperature=self._cfg.temperature,
                                    max_new_tokens=self._cfg.maxNewTokens,
                                    without_timestamps=True,
                                    condition_on_previous_text=False,
                                )
                                translated_window_text = " ".join(
                                    segment.text.strip() for segment in translated_segments if segment.text.strip()
                                ).strip()
                                translated_stable_text = _stable_window_text(
                                    translated_window_text,
                                    commit_lag_seconds,
                                    window_seconds,
                                )
                                translated_text = _new_text_delta(committed_translation_text, translated_stable_text)
                                target_language = "en"
                            else:
                                translated_text = text_translator.translate(
                                    TranslationRequest(
                                        text=sentence,
                                        source_language=source_language,
                                        target_language=target_language,
                                    )
                                )
                            translation_elapsed += time.perf_counter() - translation_started_at
                            if translated_text:
                                if is_final_translation:
                                    committed_translation_text = _append_committed_text(committed_translation_text, translated_text)
                                self._emit(
                                    "translation",
                                    translated_text,
                                    log_text=f"[{detected}->{target_language}] {translated_text}",
                                    final=is_final_translation,
                                )
                            else:
                                self._emit("status", f"Whisper 번역 결과 없음: chunk={chunks}", display=False)
                    except Exception as exc:
                        translation_elapsed = time.perf_counter() - translation_started_at if translation_attempted else 0.0
                        translation_failed = True
                        self._emit(
                            "error",
                            "Whisper 번역 실패: "
                            f"{exc}. 번역을 이번 세션에서 중지합니다. STT 전사는 계속됩니다.",
                        )
                total_elapsed = time.perf_counter() - chunk_started_at
                self._emit(
                    "status",
                    "Whisper 성능: "
                    f"chunk={chunks} step={step_seconds:.2f}s window={window_seconds:.2f}s "
                    f"commit_lag={commit_lag_seconds:.2f}s audio={chunk_audio_seconds:.2f}s "
                    f"stt={stt_elapsed:.2f}s stt_rtf={stt_elapsed / max(chunk_audio_seconds, 0.001):.2f} "
                    f"translation={translation_elapsed:.2f}s translation_enabled={self._cfg.translationEnabled and not translation_failed} "
                    f"total={total_elapsed:.2f}s total_rtf={total_elapsed / max(chunk_audio_seconds, 0.001):.2f} "
                    f"beam={self._cfg.beamSize} max_tokens={self._cfg.maxNewTokens} text_chars={len(text)}",
                    display=False,
                )
            except Exception as exc:
                self._emit("error", f"Whisper 전사 실패: {exc}")

    def _run_mock(self) -> None:
        self._emit("status", "Whisper mock 출력 시작")
        index = 1
        while not self._stop.is_set():
            self._emit("transcript", f"[mock] sample transcript {index}")
            if self._cfg.translationEnabled:
                self._emit("translation", f"translated mock sample {index}", log_text=f"[mock->{self._cfg.translationTargetLanguage}] translated mock sample {index}")
            index += 1
            self._stop.wait(2.0)


class WhisperTranscriptWindow:
    def __init__(self, app_config: AppConfig, config_path: Path) -> None:
        if not app_config.whisper.enabled:
            raise RuntimeError("whisper.enabled=false 입니다. config에서 Whisper STT를 켠 뒤 serve를 실행하세요.")
        try:
            import tkinter as tk
            from tkinter import ttk
        except ModuleNotFoundError as exc:
            raise RuntimeError("Tkinter가 없습니다. Whisper 출력 창을 열 수 없습니다.") from exc

        self._tk = tk
        self._ttk = ttk
        self._config_path = config_path
        self._ui_language = _load_ui_language(config_path)
        self._whisper_config = app_config.whisper
        self._geometry_save_after_id: str | None = None
        self._translation_geometry_save_after_id: str | None = None
        self._translation_root = None
        self._translation_text = None
        self._line_number_widgets = {}
        self._context_text = None
        self._transcript_partial_active = False
        self._translation_partial_active = False
        self._events: queue.Queue[TranscriptEvent] = queue.Queue()
        self._worker = WhisperTranscriptWorker(app_config.whisper, self._events)
        self._thread = threading.Thread(target=self._worker.run, daemon=True)
        self._root = tk.Tk()
        self._root.title(_window_title("transcript", self._ui_language))
        restored_geometry = _load_window_geometry(self._config_path, "whisperWindowGeometry", self._root)
        self._root.geometry(restored_geometry or DEFAULT_WINDOW_GEOMETRY)
        self._root.minsize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        self._root.columnconfigure(0, weight=1)
        self._root.rowconfigure(0, weight=1)

        frame = ttk.Frame(self._root, padding=10)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(0, weight=1)

        self._text = self._create_numbered_text(frame, 0)
        self._context_menu = tk.Menu(self._root, tearoff=False)
        self._context_menu.add_command(label="Copy", command=self._copy_selection)
        self._context_menu.add_command(label="Copy All", command=self._copy_all)
        self._context_menu.add_separator()
        self._context_menu.add_command(label="Clear", command=self._clear)

        actions = ttk.Frame(frame)
        actions.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        actions.columnconfigure(0, weight=1)
        copy_btn = ttk.Button(actions, text="Copy All", command=lambda: self._copy_all(self._text))
        copy_btn.grid(row=0, column=1, sticky="e", padx=(0, 6))
        clear_btn = ttk.Button(actions, text="Clear", command=lambda: self._clear(self._text))
        clear_btn.grid(row=0, column=2, sticky="e")

        if self._whisper_config.translationEnabled:
            self._create_translation_window()

        self._root.bind("<Configure>", self._on_configure)
        self._root.protocol("WM_DELETE_WINDOW", self._close)


    def _create_translation_window(self) -> None:
        tk = self._tk
        ttk = self._ttk
        self._translation_root = tk.Toplevel(self._root)
        self._translation_root.title(_window_title("translation", self._ui_language))
        restored_geometry = _load_window_geometry(
            self._config_path, "whisperTranslationWindowGeometry", self._translation_root
        )
        self._translation_root.geometry(restored_geometry or DEFAULT_WINDOW_GEOMETRY)
        self._translation_root.minsize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        self._translation_root.columnconfigure(0, weight=1)
        self._translation_root.rowconfigure(0, weight=1)

        frame = ttk.Frame(self._translation_root, padding=10)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(0, weight=1)

        self._translation_text = self._create_numbered_text(frame, 0)

        actions = ttk.Frame(frame)
        actions.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        actions.columnconfigure(0, weight=1)
        copy_btn = ttk.Button(actions, text="Copy All", command=lambda: self._copy_all(self._translation_text))
        copy_btn.grid(row=0, column=1, sticky="e", padx=(0, 6))
        clear_btn = ttk.Button(actions, text="Clear", command=lambda: self._clear(self._translation_text))
        clear_btn.grid(row=0, column=2, sticky="e")

        self._translation_root.bind("<Configure>", self._on_translation_configure)
        self._translation_root.protocol("WM_DELETE_WINDOW", self._hide_translation_window)

    def _create_numbered_text(self, parent, row: int):
        tk = self._tk
        ttk = self._ttk
        line_numbers = tk.Canvas(parent, width=self._line_number_width(1), highlightthickness=0, takefocus=False)
        line_numbers.grid(row=row, column=0, sticky="ns")
        text_widget = tk.Text(parent, wrap="word", undo=False)
        self._configure_transcript_text_tags(text_widget)
        text_widget.grid(row=row, column=1, sticky="nsew")
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=text_widget.yview)
        scrollbar.grid(row=row, column=2, sticky="ns")

        def yscroll(first: str, last: str) -> None:
            scrollbar.set(first, last)
            self._update_line_numbers(text_widget)

        text_widget.configure(yscrollcommand=yscroll)
        text_widget.bind("<Key>", self._on_text_key)
        text_widget.bind("<Button-3>", self._show_context_menu)
        text_widget.bind("<Control-Button-1>", self._show_context_menu)
        text_widget.bind("<Configure>", lambda _event: self._update_line_numbers(text_widget))
        self._configure_line_number_text(line_numbers)
        self._line_number_widgets[text_widget] = line_numbers
        return text_widget

    def _configure_line_number_text(self, line_numbers) -> None:
        line_numbers.configure(background="#f0f0f0")

    def _line_number_width(self, max_line: int) -> int:
        digits = max(1, len(str(max_line)))
        return max(42, (digits * 9) + 16)

    def _line_number_x(self, max_line: int) -> int:
        return self._line_number_width(max_line) - 6

    def _update_line_numbers(self, text_widget) -> None:
        line_numbers = getattr(self, "_line_number_widgets", {}).get(text_widget)
        if line_numbers is None:
            return
        line_numbers.delete("all")
        try:
            index = text_widget.index("@0,0")
            visible_lines: list[tuple[str, int]] = []
            while True:
                info = text_widget.dlineinfo(index)
                if info is None:
                    break
                line = index.split(".", 1)[0]
                visible_lines.append((line, info[1]))
                next_index = text_widget.index(f"{index}+1line")
                if next_index == index:
                    break
                index = next_index
            max_line = max((int(line) for line, _y in visible_lines), default=1)
            line_numbers.configure(width=self._line_number_width(max_line))
            x = self._line_number_x(max_line)
            for line, y in visible_lines:
                line_numbers.create_text(x, y, anchor="ne", text=line, fill="#777777")
        except Exception:
            content = text_widget.get("1.0", "end-1c")
            line_count = 0 if not content else content.count("\n") + 1
            line_numbers.configure(width=self._line_number_width(line_count))
            x = self._line_number_x(line_count)
            for line in range(1, line_count + 1):
                line_numbers.create_text(x, (line - 1) * 17, anchor="ne", text=str(line), fill="#777777")

    def run(self) -> int:
        self._thread.start()
        self._root.after(100, self._poll_events)
        self._root.mainloop()
        return 0

    def _on_text_key(self, event) -> str | None:
        if (event.state & 0x4) and event.keysym.lower() in {"c", "a"}:
            if event.keysym.lower() == "a":
                event.widget.tag_add("sel", "1.0", "end-1c")
                return "break"
            return None
        return "break"

    def _configure_transcript_text_tags(self, text_widget) -> None:
        text_widget.tag_configure(FINAL_TEXT_TAG, foreground=FINAL_TEXT_COLOR)
        text_widget.tag_configure(PARTIAL_TEXT_TAG, foreground=PARTIAL_TEXT_COLOR)

    def _append(self, line: str, text_widget=None, *, final: bool = True) -> None:
        target = text_widget if text_widget is not None else self._text
        partial_attr = None
        if target is self._text:
            partial_attr = "_transcript_partial_active"
        elif target is self._translation_text:
            partial_attr = "_translation_partial_active"
        if partial_attr is not None and getattr(self, partial_attr):
            target.delete("end-1c linestart", "end-1c")
        if final:
            target.insert("end", f"{line}\n", FINAL_TEXT_TAG)
            if partial_attr is not None:
                setattr(self, partial_attr, False)
        else:
            target.insert("end", line, PARTIAL_TEXT_TAG)
            if partial_attr is not None:
                setattr(self, partial_attr, True)
        self._update_line_numbers(target)
        target.see("end")

    def _poll_events(self) -> None:
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            if not _is_modal_output_event(event):
                continue
            if event.kind == "translation" and self._translation_text is not None:
                self._append(event.text, self._translation_text, final=event.final)
            elif event.kind == "transcript":
                self._append(event.text, self._text, final=event.final)
        self._root.after(100, self._poll_events)

    def _on_configure(self, event) -> None:
        if event.widget != self._root:
            return
        if self._geometry_save_after_id is not None:
            try:
                self._root.after_cancel(self._geometry_save_after_id)
            except Exception:
                pass
        self._geometry_save_after_id = self._root.after(600, self._save_geometry)

    def _on_translation_configure(self, event) -> None:
        if self._translation_root is None or event.widget != self._translation_root:
            return
        if self._translation_geometry_save_after_id is not None:
            try:
                self._translation_root.after_cancel(self._translation_geometry_save_after_id)
            except Exception:
                pass
        self._translation_geometry_save_after_id = self._translation_root.after(600, self._save_translation_geometry)

    def _current_geometry(self) -> str:
        try:
            self._root.update_idletasks()
        except Exception:
            pass
        return self._root.winfo_geometry()

    def _save_geometry(self) -> None:
        self._geometry_save_after_id = None
        _save_window_geometry(
            self._config_path,
            "whisperWindowGeometry",
            self._current_geometry(),
            *_window_restore_extent(self._root),
        )

    def _save_translation_geometry(self) -> None:
        self._translation_geometry_save_after_id = None
        if self._translation_root is None:
            return
        _save_window_geometry(
            self._config_path,
            "whisperTranslationWindowGeometry",
            _window_manager_geometry(self._translation_root),
            *_window_restore_extent(self._translation_root),
        )

    def _show_context_menu(self, event) -> str:
        self._context_text = event.widget
        try:
            has_selection = bool(event.widget.tag_ranges("sel"))
            self._context_menu.entryconfigure("Copy", state="normal" if has_selection else "disabled")
            self._context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._context_menu.grab_release()
        return "break"

    def _copy_selection(self) -> None:
        target = self._context_text if self._context_text is not None else self._text
        try:
            text = target.get("sel.first", "sel.last")
        except Exception:
            return
        self._root.clipboard_clear()
        self._root.clipboard_append(text)

    def _copy_all(self, text_widget=None) -> None:
        target = text_widget if text_widget is not None else (self._context_text or self._text)
        text = target.get("1.0", "end-1c")
        self._root.clipboard_clear()
        self._root.clipboard_append(text)

    def _clear(self, text_widget=None) -> None:
        target = text_widget if text_widget is not None else (self._context_text or self._text)
        target.delete("1.0", "end")
        self._update_line_numbers(target)
        if target is self._text:
            self._transcript_partial_active = False
        elif target is self._translation_text:
            self._translation_partial_active = False

    def _hide_translation_window(self) -> None:
        if self._translation_root is not None:
            self._save_translation_geometry()
            self._translation_root.withdraw()

    def _close(self) -> None:
        if self._geometry_save_after_id is not None:
            try:
                self._root.after_cancel(self._geometry_save_after_id)
            except Exception:
                pass
            self._geometry_save_after_id = None
        if self._translation_geometry_save_after_id is not None and self._translation_root is not None:
            try:
                self._translation_root.after_cancel(self._translation_geometry_save_after_id)
            except Exception:
                pass
            self._translation_geometry_save_after_id = None
        self._save_geometry()
        self._save_translation_geometry()
        self._worker.stop()
        if self._translation_root is not None:
            try:
                self._translation_root.destroy()
            except Exception:
                pass
        self._root.after(100, self._root.destroy)


def main() -> int:
    log_path = install_rotating_stdout_log("avc-whisper")
    _log_line(f"[avc] whisper rotating log file: {log_path}")
    args = parse_args()
    config_path = Path(args.config).expanduser()
    app_config = AppConfig.load(config_path)
    window = WhisperTranscriptWindow(app_config, config_path)
    return window.run()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        _log_line(f"[avc] whisper window failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
