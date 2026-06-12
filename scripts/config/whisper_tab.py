from __future__ import annotations

from scripts.config.whisper_options import (
    whisper_backend_options,
    whisper_language_display_from_raw,
    whisper_language_options,
    whisper_model_options,
    whisper_translation_backend_options,
    whisper_translation_model_options,
    whisper_translation_target_display_from_raw,
    whisper_translation_target_options,
)


def _add_hint(gui, ttk, parent, row: int, key: str, default: str) -> int:
    hint = ttk.Label(
        parent,
        text=gui._tr(key, default),
        foreground="#666",
        wraplength=520,
    )
    hint.grid(row=row, column=0, columnspan=4, sticky="w", padx=4, pady=(2, 6))
    gui._register_localized_widget(hint, key, default)
    return row + 1


def build_whisper_tab(
    gui,
    tab_whisper,
    ttk,
    audio_input_device_candidates,
    audio_default_input_device,
    audio_device_display_values,
) -> None:
    row = 0
    gui._add_bool_switch(
        tab_whisper,
        row,
        "whisper_enabled",
        gui._tr("label.whisper_enabled", "Whisper STT"),
        False,
        label_key="label.whisper_enabled",
    )
    row += 1

    whisper_input_candidates = audio_input_device_candidates()
    whisper_input_default = audio_default_input_device()
    if whisper_input_default not in whisper_input_candidates:
        whisper_input_candidates.append(whisper_input_default)
    whisper_input_display_values, gui._whisper_input_display_to_raw = audio_device_display_values(
        "input", whisper_input_candidates
    )
    whisper_input_default_display = next(
        (k for k, v in gui._whisper_input_display_to_raw.items() if v == whisper_input_default),
        whisper_input_default,
    )
    gui._add_combo(
        tab_whisper,
        row,
        "whisper_input_device",
        gui._tr("label.whisper_input_device", "Input device"),
        whisper_input_display_values,
        whisper_input_default_display,
        label_key="label.whisper_input_device",
    )
    row += 1

    whisper_input_meter_btn = ttk.Button(
        tab_whisper,
        text=gui._tr("button.whisper_input_meter", "Whisper input dB meter"),
        command=gui._run_whisper_input_meter,
    )
    gui._register_localized_widget(whisper_input_meter_btn, "button.whisper_input_meter", "Whisper input dB meter")
    whisper_input_meter_btn.grid(row=row, column=0, columnspan=4, sticky="ew", padx=4, pady=(6, 0))
    row += 1

    gui._add_combo(
        tab_whisper,
        row,
        "whisper_backend",
        gui._tr("label.whisper_backend", "Whisper backend"),
        whisper_backend_options(),
        whisper_backend_options()[0],
        label_key="label.whisper_backend",
    )
    row += 1
    gui._add_combo(
        tab_whisper,
        row,
        "whisper_model",
        gui._tr("label.whisper_model", "Whisper model"),
        whisper_model_options(),
        "base",
        label_key="label.whisper_model",
    )
    row += 1
    gui._add_combo(
        tab_whisper,
        row,
        "whisper_language",
        gui._tr("label.whisper_language", "Recognition language (single choice)"),
        whisper_language_options(),
        whisper_language_display_from_raw("ko"),
        label_key="label.whisper_language",
    )
    row += 1
    row = _add_hint(
        gui,
        ttk,
        tab_whisper,
        row,
        "hint.whisper_language",
        "Whisper accepts one recognition language. Use auto detection when Korean, English, and Chinese are mixed.",
    )

    gui._add_combo(
        tab_whisper,
        row,
        "whisper_device",
        gui._tr("label.whisper_device", "STT device"),
        ["auto", "cpu", "cuda", "mps"],
        "cuda",
        label_key="label.whisper_device",
    )
    row += 1
    gui._add_combo(
        tab_whisper,
        row,
        "whisper_compute_type",
        gui._tr("label.whisper_compute_type", "STT compute type"),
        ["auto", "int8", "float16", "float32"],
        "auto",
        label_key="label.whisper_compute_type",
    )
    row += 1
    gui._add_bool_switch(
        tab_whisper,
        row,
        "whisper_vad_filter",
        gui._tr("label.whisper_vad_filter", "VAD filter"),
        True,
        label_key="label.whisper_vad_filter",
    )
    row += 1
    gui._add_slider(
        tab_whisper,
        row,
        "whisper_chunk_seconds",
        gui._tr("label.whisper_chunk_seconds", "Chunk seconds"),
        5.0,
        1.0,
        10.0,
        resolution=0.5,
        label_key="label.whisper_chunk_seconds",
    )
    row += 1
    gui._add_slider(
        tab_whisper,
        row,
        "whisper_beam_size",
        gui._tr("label.whisper_beam_size", "Beam size"),
        5,
        1,
        8,
        resolution=1,
        label_key="label.whisper_beam_size",
    )
    row += 1
    row = _add_hint(
        gui,
        ttk,
        tab_whisper,
        row,
        "hint.whisper_speed",
        "Lower STT chunk seconds and beam size improve response speed, but may reduce accuracy or sentence continuity.",
    )

    gui._add_bool_switch(
        tab_whisper,
        row,
        "whisper_translation_enabled",
        gui._tr("label.whisper_translation_enabled", "Translation window"),
        False,
        label_key="label.whisper_translation_enabled",
    )
    row += 1
    gui._add_combo(
        tab_whisper,
        row,
        "whisper_translation_backend",
        gui._tr("label.whisper_translation_backend", "Translation backend"),
        whisper_translation_backend_options(),
        "whisper",
        label_key="label.whisper_translation_backend",
    )
    row += 1

    whisper_translation_frame = ttk.Frame(tab_whisper)
    whisper_translation_frame.grid(row=row, column=0, columnspan=4, sticky="ew", padx=0, pady=(0, 4))
    whisper_translation_frame.columnconfigure(0, weight=1)
    _add_hint(
        gui,
        ttk,
        whisper_translation_frame,
        0,
        "hint.whisper_translation_whisper_backend",
        "Whisper translation outputs English only and does not use the external translation model settings.",
    )
    row += 1

    nllb_translation_frame = ttk.Frame(tab_whisper)
    nllb_translation_frame.grid(row=row, column=0, columnspan=4, sticky="ew", padx=0, pady=(0, 4))
    for col in range(4):
        nllb_translation_frame.columnconfigure(col, weight=1 if col in (1, 3) else 0)
    nllb_row = 0
    gui._add_combo(
        nllb_translation_frame,
        nllb_row,
        "whisper_translation_target_language",
        gui._tr("label.whisper_translation_target_language", "Translation target language"),
        whisper_translation_target_options(),
        whisper_translation_target_display_from_raw("en"),
        label_key="label.whisper_translation_target_language",
    )
    nllb_row += 1
    gui._add_combo(
        nllb_translation_frame,
        nllb_row,
        "whisper_translation_model",
        gui._tr("label.whisper_translation_model", "Translation model"),
        whisper_translation_model_options(),
        whisper_translation_model_options()[0],
        label_key="label.whisper_translation_model",
    )
    nllb_row += 1
    gui._add_combo(
        nllb_translation_frame,
        nllb_row,
        "whisper_translation_device",
        gui._tr("label.whisper_translation_device", "Translation device"),
        ["cuda"],
        "cuda",
        label_key="label.whisper_translation_device",
    )
    nllb_row += 1
    gui._add_combo(
        nllb_translation_frame,
        nllb_row,
        "whisper_translation_compute_type",
        gui._tr("label.whisper_translation_compute_type", "Translation compute type"),
        ["float16", "float32"],
        "float16",
        label_key="label.whisper_translation_compute_type",
    )
    nllb_row += 1
    _add_hint(
        gui,
        ttk,
        nllb_translation_frame,
        nllb_row,
        "hint.whisper_translation_target_language",
        "NLLB translation uses the external model and requires CUDA for real-time performance.",
    )
    gui._whisper_translation_backend_frames = {
        "whisper": whisper_translation_frame,
        "mock": whisper_translation_frame,
        "nllb-transformers": nllb_translation_frame,
    }
    row += 1

    reset_whisper_btn = ttk.Button(
        tab_whisper,
        text=gui._tr("button.reset_whisper_settings", "Restore Whisper defaults"),
        command=gui._reset_whisper_settings,
    )
    gui._register_localized_widget(reset_whisper_btn, "button.reset_whisper_settings", "Restore Whisper defaults")
    reset_whisper_btn.grid(row=row, column=0, columnspan=4, sticky="ew", padx=4, pady=(6, 0))
