from __future__ import annotations

from src.domain.whisper_defaults import whisper_default

from scripts.config.whisper_options import (
    whisper_backend_options,
    whisper_language_display_from_raw,
    whisper_language_options,
    whisper_model_options,
    whisper_sentence_boundary_backend_options,
    whisper_sentence_boundary_model_options,
    whisper_stt_backend_options,
    whisper_stt_model_options,
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


def _add_group(gui, ttk, parent, row: int, key: str, default: str):
    frame = ttk.LabelFrame(parent, text=gui._tr(key, default))
    gui._register_localized_widget(frame, key, default)
    frame.grid(row=row, column=0, columnspan=4, sticky="ew", padx=4, pady=(4, 8))
    for col in range(4):
        frame.columnconfigure(col, weight=1 if col in (1, 2, 3) else 0)
    return frame, row + 1


def build_whisper_tab(
    gui,
    tab_whisper,
    ttk,
    audio_input_device_candidates,
    audio_default_input_device,
    audio_device_display_values,
) -> None:
    gui._whisper_tab = tab_whisper
    row = 0

    input_frame, row = _add_group(gui, ttk, tab_whisper, row, "label.whisper_group_input", "입력/실행")
    input_row = 0
    gui._add_bool_switch(
        input_frame,
        input_row,
        "whisper_enabled",
        gui._tr("label.whisper_enabled", "Whisper 음성 인식"),
        False,
        label_key="label.whisper_enabled",
    )
    input_row += 1

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
        input_frame,
        input_row,
        "whisper_input_device",
        gui._tr("label.whisper_input_device", "입력 장치"),
        whisper_input_display_values,
        whisper_input_default_display,
        label_key="label.whisper_input_device",
    )
    input_row += 1

    whisper_input_meter_btn = ttk.Button(
        input_frame,
        text=gui._tr("button.whisper_input_meter", "Whisper 입력 dB 미터"),
        command=gui._run_whisper_input_meter,
    )
    gui._register_localized_widget(whisper_input_meter_btn, "button.whisper_input_meter", "Whisper 입력 dB 미터")
    whisper_input_meter_btn.grid(row=input_row, column=0, columnspan=4, sticky="ew", padx=4, pady=(6, 0))

    stt_frame, row = _add_group(gui, ttk, tab_whisper, row, "label.whisper_group_stt", "STT 언어/모델")
    stt_row = 0
    gui._add_combo(
        stt_frame,
        stt_row,
        "whisper_language",
        gui._tr("label.whisper_language", "인식 언어(단일 선택)"),
        whisper_language_options(),
        whisper_language_display_from_raw(whisper_default("language")),
        label_key="label.whisper_language",
    )
    stt_row += 1
    stt_row = _add_hint(
        gui,
        ttk,
        stt_frame,
        stt_row,
        "hint.whisper_language",
        "Whisper는 한 번에 하나의 인식 언어를 사용합니다. 자동 감지는 사용하지 않으며, 현재 입력 언어를 한국어/영어/중국어 중 하나로 명시하세요.",
    )

    global_backend_row = stt_row
    gui._add_combo(
        stt_frame,
        stt_row,
        "whisper_backend",
        gui._tr("label.whisper_backend", "Whisper 백엔드"),
        whisper_backend_options(),
        whisper_default("backend"),
        label_key="label.whisper_backend",
    )
    stt_row += 1
    global_model_row = stt_row
    gui._add_combo(
        stt_frame,
        stt_row,
        "whisper_model",
        gui._tr("label.whisper_model", "Whisper 모델"),
        whisper_model_options(),
        whisper_default("model"),
        label_key="label.whisper_model",
    )
    stt_row += 1
    gui._whisper_global_stt_parent = stt_frame
    gui._whisper_global_stt_rows = [global_backend_row, global_model_row]

    stt_language_rows = {}
    for lang_code, lang_label in (("en", "영어"), ("ko", "한국어"), ("zh", "중국어")):
        lang_rows = []
        backend_key = f"whisper_stt_backend_{lang_code}"
        model_key = f"whisper_stt_model_{lang_code}"
        backend_default = whisper_default(f"sttBackend{lang_code.title()}")
        model_default = whisper_default(f"sttModel{lang_code.title()}")
        lang_rows.append(stt_row)
        gui._add_combo(
            stt_frame,
            stt_row,
            backend_key,
            gui._tr(f"label.{backend_key}", f"{lang_label} STT 모델 타입"),
            whisper_stt_backend_options(lang_code),
            backend_default,
            label_key=f"label.{backend_key}",
        )
        stt_row += 1
        lang_rows.append(stt_row)
        gui._add_combo(
            stt_frame,
            stt_row,
            model_key,
            gui._tr(f"label.{model_key}", f"{lang_label} STT 모델"),
            whisper_stt_model_options(backend_default, lang_code),
            model_default,
            label_key=f"label.{model_key}",
        )
        stt_row += 1
        stt_language_rows[lang_code] = lang_rows
    gui._whisper_stt_frame = stt_frame
    gui._whisper_stt_language_rows = stt_language_rows
    _add_hint(
        gui,
        ttk,
        stt_frame,
        stt_row,
        "hint.whisper_stt_models",
        "STT 모델 타입과 모델은 위의 인식 언어에 맞는 항목만 표시합니다. 언어를 바꾸면 해당 언어의 백엔드와 모델 후보로 전환되며, 기본값은 유지됩니다.",
    )

    runtime_frame, row = _add_group(gui, ttk, tab_whisper, row, "label.whisper_group_runtime", "STT 응답/성능")
    runtime_row = 0
    gui._add_combo(
        runtime_frame,
        runtime_row,
        "whisper_device",
        gui._tr("label.whisper_device", "STT 장치"),
        ["auto", "cpu", "cuda", "mps"],
        whisper_default("device"),
        label_key="label.whisper_device",
    )
    runtime_row += 1
    whisper_compute_type_row = runtime_row
    gui._add_combo(
        runtime_frame,
        runtime_row,
        "whisper_compute_type",
        gui._tr("label.whisper_compute_type", "STT 연산 타입"),
        ["auto", "int8", "float16", "float32"],
        whisper_default("computeType"),
        label_key="label.whisper_compute_type",
    )
    runtime_row += 1
    gui._add_slider(
        runtime_frame,
        runtime_row,
        "whisper_step_seconds",
        gui._tr("label.whisper_step_seconds", "업데이트 간격(초)"),
        whisper_default("stepSeconds"),
        0.5,
        5.0,
        resolution=0.5,
        label_key="label.whisper_step_seconds",
    )
    runtime_row += 1
    gui._add_slider(
        runtime_frame,
        runtime_row,
        "whisper_window_seconds",
        gui._tr("label.whisper_window_seconds", "컨텍스트 윈도우(초)"),
        whisper_default("windowSeconds"),
        1.0,
        15.0,
        resolution=0.5,
        label_key="label.whisper_window_seconds",
    )
    runtime_row += 1
    gui._add_slider(
        runtime_frame,
        runtime_row,
        "whisper_commit_lag_seconds",
        gui._tr("label.whisper_commit_lag_seconds", "확정 지연(초)"),
        whisper_default("commitLagSeconds"),
        0.0,
        5.0,
        resolution=0.5,
        label_key="label.whisper_commit_lag_seconds",
    )
    runtime_row += 1
    whisper_beam_size_row = runtime_row
    gui._add_slider(
        runtime_frame,
        runtime_row,
        "whisper_beam_size",
        gui._tr("label.whisper_beam_size", "Beam 크기"),
        whisper_default("beamSize"),
        1,
        8,
        resolution=1,
        label_key="label.whisper_beam_size",
    )
    runtime_row += 1
    whisper_max_new_tokens_row = runtime_row
    gui._add_slider(
        runtime_frame,
        runtime_row,
        "whisper_max_new_tokens",
        gui._tr("label.whisper_max_new_tokens", "STT 최대 토큰"),
        whisper_default("maxNewTokens"),
        16,
        512,
        resolution=16,
        label_key="label.whisper_max_new_tokens",
    )
    runtime_row += 1
    whisper_temperature_row = runtime_row
    gui._add_slider(
        runtime_frame,
        runtime_row,
        "whisper_temperature",
        gui._tr("label.whisper_temperature", "STT temperature"),
        whisper_default("temperature"),
        0.0,
        1.0,
        resolution=0.1,
        label_key="label.whisper_temperature",
    )
    runtime_row += 1
    _add_hint(
        gui,
        ttk,
        runtime_frame,
        runtime_row,
        "hint.whisper_speed",
        "업데이트 간격/컨텍스트/확정 지연은 공통 STT 스트리밍 설정입니다. Beam, 최대 토큰, temperature, 연산 타입은 선택한 STT 모델 타입이 지원할 때만 표시됩니다.",
    )
    gui._whisper_backend_option_parent = runtime_frame
    gui._whisper_backend_option_rows = {
        "compute_type": whisper_compute_type_row,
        "beam_size": whisper_beam_size_row,
        "max_new_tokens": whisper_max_new_tokens_row,
        "temperature": whisper_temperature_row,
    }
    gui._whisper_backend_specific_rows = list(gui._whisper_backend_option_rows.values())

    boundary_frame, row = _add_group(gui, ttk, tab_whisper, row, "label.whisper_group_boundary", "문장 경계")
    boundary_row = 0
    manual_boundary_backend_row = boundary_row
    gui._add_combo(
        boundary_frame,
        boundary_row,
        "whisper_sentence_boundary_backend",
        gui._tr("label.whisper_sentence_boundary_backend", "수동 문장 경계 백엔드"),
        whisper_sentence_boundary_backend_options(),
        whisper_default("sentenceBoundaryBackend"),
        label_key="label.whisper_sentence_boundary_backend",
    )
    boundary_row += 1
    manual_boundary_model_row = boundary_row
    gui._add_combo(
        boundary_frame,
        boundary_row,
        "whisper_sentence_boundary_model",
        gui._tr("label.whisper_sentence_boundary_model", "수동 문장 경계 모델"),
        whisper_sentence_boundary_model_options(whisper_default("sentenceBoundaryBackend")),
        whisper_default("sentenceBoundaryModel"),
        label_key="label.whisper_sentence_boundary_model",
    )
    boundary_row += 1
    manual_boundary_hint_row = boundary_row
    _add_hint(
        gui,
        ttk,
        boundary_frame,
        boundary_row,
        "hint.whisper_sentence_boundary_manual",
        "문장 경계 backend/model은 모든 언어에서 이 수동 설정을 사용합니다.",
    )
    gui._whisper_manual_boundary_parent = boundary_frame
    gui._whisper_manual_boundary_rows = [manual_boundary_backend_row, manual_boundary_model_row, manual_boundary_hint_row]

    translation_group, row = _add_group(gui, ttk, tab_whisper, row, "label.whisper_group_translation", "번역")
    translation_row = 0
    gui._add_bool_switch(
        translation_group,
        translation_row,
        "whisper_translation_enabled",
        gui._tr("label.whisper_translation_enabled", "번역 창"),
        whisper_default("translationEnabled"),
        label_key="label.whisper_translation_enabled",
    )
    translation_row += 1
    gui._add_combo(
        translation_group,
        translation_row,
        "whisper_translation_backend",
        gui._tr("label.whisper_translation_backend", "번역 백엔드"),
        whisper_translation_backend_options(),
        whisper_default("translationBackend"),
        label_key="label.whisper_translation_backend",
    )
    translation_row += 1

    whisper_translation_frame = ttk.Frame(translation_group)
    whisper_translation_frame.grid(row=translation_row, column=0, columnspan=4, sticky="ew", padx=0, pady=(0, 4))
    whisper_translation_frame.columnconfigure(0, weight=1)
    _add_hint(
        gui,
        ttk,
        whisper_translation_frame,
        0,
        "hint.whisper_translation_whisper_backend",
        "Whisper 번역은 영어 출력만 지원하며 외부 번역 모델 설정을 사용하지 않습니다.",
    )
    translation_row += 1

    nllb_translation_frame = ttk.Frame(translation_group)
    nllb_translation_frame.grid(row=translation_row, column=0, columnspan=4, sticky="ew", padx=0, pady=(0, 4))
    for col in range(4):
        nllb_translation_frame.columnconfigure(col, weight=1 if col in (1, 3) else 0)
    nllb_row = 0
    gui._add_combo(
        nllb_translation_frame,
        nllb_row,
        "whisper_translation_target_language",
        gui._tr("label.whisper_translation_target_language", "번역 대상 언어"),
        whisper_translation_target_options(),
        whisper_translation_target_display_from_raw(whisper_default("translationTargetLanguage")),
        label_key="label.whisper_translation_target_language",
    )
    nllb_row += 1
    gui._add_combo(
        nllb_translation_frame,
        nllb_row,
        "whisper_translation_model",
        gui._tr("label.whisper_translation_model", "번역 모델"),
        whisper_translation_model_options(),
        whisper_default("translationModel"),
        label_key="label.whisper_translation_model",
    )
    nllb_row += 1
    gui._add_combo(
        nllb_translation_frame,
        nllb_row,
        "whisper_translation_device",
        gui._tr("label.whisper_translation_device", "번역 장치"),
        ["cuda"],
        whisper_default("translationDevice"),
        label_key="label.whisper_translation_device",
    )
    nllb_row += 1
    gui._add_combo(
        nllb_translation_frame,
        nllb_row,
        "whisper_translation_compute_type",
        gui._tr("label.whisper_translation_compute_type", "번역 연산 타입"),
        ["float16", "float32"],
        whisper_default("translationComputeType"),
        label_key="label.whisper_translation_compute_type",
    )
    nllb_row += 1
    gui._add_slider(
        nllb_translation_frame,
        nllb_row,
        "whisper_translation_beam_size",
        gui._tr("label.whisper_translation_beam_size", "번역 Beam 크기"),
        whisper_default("translationBeamSize"),
        1,
        8,
        resolution=1,
        label_key="label.whisper_translation_beam_size",
    )
    nllb_row += 1
    gui._add_slider(
        nllb_translation_frame,
        nllb_row,
        "whisper_translation_max_new_tokens",
        gui._tr("label.whisper_translation_max_new_tokens", "번역 최대 토큰"),
        whisper_default("translationMaxNewTokens"),
        16,
        512,
        resolution=16,
        label_key="label.whisper_translation_max_new_tokens",
    )
    nllb_row += 1
    _add_hint(
        gui,
        ttk,
        nllb_translation_frame,
        nllb_row,
        "hint.whisper_translation_target_language",
        "NLLB 번역은 외부 번역 모델을 사용하며 실시간 성능을 위해 CUDA가 필요합니다.",
    )
    gui._whisper_translation_backend_frames = {
        "whisper": whisper_translation_frame,
        "mock": whisper_translation_frame,
        "nllb-transformers": nllb_translation_frame,
    }

    reset_whisper_btn = ttk.Button(
        tab_whisper,
        text=gui._tr("button.reset_whisper_settings", "Whisper 기본값 복원"),
        command=gui._reset_whisper_settings,
    )
    gui._register_localized_widget(reset_whisper_btn, "button.reset_whisper_settings", "Whisper 기본값 복원")
    reset_whisper_btn.grid(row=row, column=0, columnspan=4, sticky="ew", padx=4, pady=(6, 0))
