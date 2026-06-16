from __future__ import annotations

from src.domain.dictation_ai_defaults import dictation_ai_default

from scripts.config.dictation_ai_options import (
    dictation_ai_backend_options,
    dictation_ai_language_display_from_raw,
    dictation_ai_language_options,
    dictation_ai_model_options,
    dictation_ai_sentence_boundary_backend_options,
    dictation_ai_sentence_boundary_model_options,
    dictation_ai_stt_backend_options,
    dictation_ai_stt_model_options,
    dictation_ai_translation_backend_options_for_target,
    dictation_ai_translation_model_options,
    dictation_ai_translation_target_display_from_raw,
    dictation_ai_translation_target_options,
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

    input_frame, row = _add_group(gui, ttk, tab_whisper, row, "label.dictation_ai_group_input", "입력/실행")
    input_row = 0
    gui._add_bool_switch(
        input_frame,
        input_row,
        "dictation_ai_enabled",
        gui._tr("label.dictation_ai_enabled", "받아쓰기 AI 전사"),
        False,
        label_key="label.dictation_ai_enabled",
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
        "dictation_ai_input_device",
        gui._tr("label.dictation_ai_input_device", "입력 장치"),
        whisper_input_display_values,
        whisper_input_default_display,
        label_key="label.dictation_ai_input_device",
    )
    input_row += 1

    whisper_input_meter_btn = ttk.Button(
        input_frame,
        text=gui._tr("button.dictation_ai_input_meter", "오디오 입력 데시벨 측정기"),
        command=gui._run_whisper_input_meter,
    )
    gui._widgets["dictation_ai_input_meter_button"] = whisper_input_meter_btn
    gui._register_localized_widget(whisper_input_meter_btn, "button.dictation_ai_input_meter", "오디오 입력 데시벨 측정기")
    whisper_input_meter_btn.grid(row=input_row, column=0, columnspan=4, sticky="ew", padx=4, pady=(6, 0))
    input_row += 1
    dictation_ai_model_download_btn = ttk.Button(
        input_frame,
        text=gui._tr("button.dictation_ai_model_download_selected", "모델 다운로드 매니저"),
        command=gui._show_dictation_ai_model_download_dialog_for_current_config,
    )
    gui._register_localized_widget(
        dictation_ai_model_download_btn, "button.dictation_ai_model_download_selected", "모델 다운로드 매니저"
    )
    gui._widgets["dictation_ai_model_download_button"] = dictation_ai_model_download_btn
    dictation_ai_model_download_btn.grid(row=input_row, column=0, columnspan=4, sticky="ew", padx=4, pady=(6, 0))
    input_row += 1

    stt_frame, row = _add_group(gui, ttk, tab_whisper, row, "label.dictation_ai_group_stt", "STT 언어/모델")
    stt_row = 0
    gui._add_combo(
        stt_frame,
        stt_row,
        "dictation_ai_language",
        gui._tr("label.dictation_ai_language", "인식 언어(단일 선택)"),
        dictation_ai_language_options(),
        dictation_ai_language_display_from_raw(dictation_ai_default("language")),
        label_key="label.dictation_ai_language",
    )
    stt_row += 1
    stt_row = _add_hint(
        gui,
        ttk,
        stt_frame,
        stt_row,
        "hint.dictation_ai_language",
        "받아쓰기 AI 전사는 한 번에 하나의 인식 언어를 사용합니다. 자동 감지는 사용하지 않으며, 현재 입력 언어를 한국어/영어/중국어 중 하나로 명시하세요.",
    )

    global_backend_row = stt_row
    gui._add_combo(
        stt_frame,
        stt_row,
        "dictation_ai_backend",
        gui._tr("label.dictation_ai_backend", "기본 STT 백엔드"),
        dictation_ai_backend_options(),
        dictation_ai_default("backend"),
        label_key="label.dictation_ai_backend",
    )
    stt_row += 1
    global_model_row = stt_row
    gui._add_combo(
        stt_frame,
        stt_row,
        "dictation_ai_model",
        gui._tr("label.dictation_ai_model", "기본 STT 모델"),
        dictation_ai_model_options(),
        dictation_ai_default("model"),
        label_key="label.dictation_ai_model",
    )
    stt_row += 1
    gui._whisper_global_stt_parent = stt_frame
    gui._whisper_global_stt_rows = [global_backend_row, global_model_row]

    stt_language_rows = {}
    for lang_code, lang_label in (("en", "영어"), ("ko", "한국어"), ("zh", "중국어")):
        lang_rows = []
        backend_key = f"dictation_ai_stt_backend_{lang_code}"
        model_key = f"dictation_ai_stt_model_{lang_code}"
        backend_default = dictation_ai_default(f"sttBackend{lang_code.title()}")
        model_default = dictation_ai_default(f"sttModel{lang_code.title()}")
        lang_rows.append(stt_row)
        gui._add_combo(
            stt_frame,
            stt_row,
            backend_key,
            gui._tr(f"label.{backend_key}", f"{lang_label} STT 모델 타입"),
            dictation_ai_stt_backend_options(lang_code),
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
            dictation_ai_stt_model_options(backend_default, lang_code),
            model_default,
            label_key=f"label.{model_key}",
        )
        stt_row += 1
        stt_language_rows[lang_code] = lang_rows
    gui._dictation_ai_stt_frame = stt_frame
    gui._dictation_ai_stt_language_rows = stt_language_rows
    _add_hint(
        gui,
        ttk,
        stt_frame,
        stt_row,
        "hint.dictation_ai_stt_models",
        "STT 모델 타입과 모델은 위의 인식 언어에 맞는 항목만 표시합니다. 언어를 바꾸면 해당 언어의 백엔드와 모델 후보로 전환되며, 기본값은 유지됩니다.",
    )

    runtime_frame, row = _add_group(gui, ttk, tab_whisper, row, "label.dictation_ai_group_runtime", "STT 응답/성능")
    runtime_row = 0
    gui._add_bool_switch(
        runtime_frame,
        runtime_row,
        "dictation_ai_show_stt_status_window",
        gui._tr("label.dictation_ai_show_stt_status_window", "STT 원문창 보기"),
        dictation_ai_default("showSttStatusWindow"),
        label_key="label.dictation_ai_show_stt_status_window",
    )
    runtime_row += 1
    gui._add_combo(
        runtime_frame,
        runtime_row,
        "dictation_ai_device",
        gui._tr("label.dictation_ai_device", "STT 장치"),
        ["auto", "cpu", "cuda", "mps"],
        dictation_ai_default("device"),
        label_key="label.dictation_ai_device",
    )
    runtime_row += 1
    dictation_ai_compute_type_row = runtime_row
    gui._add_combo(
        runtime_frame,
        runtime_row,
        "dictation_ai_compute_type",
        gui._tr("label.dictation_ai_compute_type", "STT 연산 타입"),
        ["auto", "int8", "float16", "float32"],
        dictation_ai_default("computeType"),
        label_key="label.dictation_ai_compute_type",
    )
    runtime_row += 1
    gui._add_slider(
        runtime_frame,
        runtime_row,
        "dictation_ai_step_seconds",
        gui._tr("label.dictation_ai_step_seconds", "업데이트 간격(초)"),
        dictation_ai_default("stepSeconds"),
        0.5,
        5.0,
        resolution=0.5,
        label_key="label.dictation_ai_step_seconds",
    )
    runtime_row += 1
    gui._add_slider(
        runtime_frame,
        runtime_row,
        "dictation_ai_window_seconds",
        gui._tr("label.dictation_ai_window_seconds", "컨텍스트 윈도우(초)"),
        dictation_ai_default("windowSeconds"),
        1.0,
        30.0,
        resolution=0.5,
        label_key="label.dictation_ai_window_seconds",
    )
    runtime_row += 1
    dictation_ai_beam_size_row = runtime_row
    gui._add_slider(
        runtime_frame,
        runtime_row,
        "dictation_ai_beam_size",
        gui._tr("label.dictation_ai_beam_size", "Beam 크기"),
        dictation_ai_default("beamSize"),
        1,
        8,
        resolution=1,
        label_key="label.dictation_ai_beam_size",
    )
    runtime_row += 1
    dictation_ai_max_new_tokens_row = runtime_row
    gui._add_slider(
        runtime_frame,
        runtime_row,
        "dictation_ai_max_new_tokens",
        gui._tr("label.dictation_ai_max_new_tokens", "STT 최대 토큰"),
        dictation_ai_default("maxNewTokens"),
        16,
        512,
        resolution=16,
        label_key="label.dictation_ai_max_new_tokens",
    )
    runtime_row += 1
    dictation_ai_temperature_row = runtime_row
    gui._add_slider(
        runtime_frame,
        runtime_row,
        "dictation_ai_temperature",
        gui._tr("label.dictation_ai_temperature", "STT temperature"),
        dictation_ai_default("temperature"),
        0.0,
        1.0,
        resolution=0.1,
        label_key="label.dictation_ai_temperature",
    )
    runtime_row += 1
    _add_hint(
        gui,
        ttk,
        runtime_frame,
        runtime_row,
        "hint.dictation_ai_speed",
        "업데이트 간격/컨텍스트는 공통 STT 스트리밍 설정입니다. 문장 확정 안정성은 STT 결과 문장 경계 처리의 문장 확정 관찰 횟수로 조정합니다. Beam, 최대 토큰, temperature, 연산 타입은 선택한 STT 모델 타입이 지원할 때만 표시됩니다.",
    )
    gui._dictation_ai_backend_option_parent = runtime_frame
    gui._dictation_ai_backend_option_rows = {
        "compute_type": dictation_ai_compute_type_row,
        "beam_size": dictation_ai_beam_size_row,
        "max_new_tokens": dictation_ai_max_new_tokens_row,
        "temperature": dictation_ai_temperature_row,
    }
    gui._dictation_ai_backend_specific_rows = list(gui._dictation_ai_backend_option_rows.values())

    boundary_frame, row = _add_group(gui, ttk, tab_whisper, row, "label.dictation_ai_group_boundary", "STT 결과 문장 경계 처리")
    boundary_row = 0
    stt_boundary_backend_row = boundary_row
    gui._add_combo(
        boundary_frame,
        boundary_row,
        "dictation_ai_sentence_boundary_backend",
        gui._tr("label.dictation_ai_sentence_boundary_backend", "STT 결과 문장 경계 처리 백엔드"),
        dictation_ai_sentence_boundary_backend_options(),
        dictation_ai_default("sentenceBoundaryBackend"),
        label_key="label.dictation_ai_sentence_boundary_backend",
    )
    boundary_row += 1
    stt_boundary_model_row = boundary_row
    gui._add_combo(
        boundary_frame,
        boundary_row,
        "dictation_ai_sentence_boundary_model",
        gui._tr("label.dictation_ai_sentence_boundary_model", "STT 결과 문장 경계 처리 모델"),
        dictation_ai_sentence_boundary_model_options(dictation_ai_default("sentenceBoundaryBackend")),
        dictation_ai_default("sentenceBoundaryModel"),
        label_key="label.dictation_ai_sentence_boundary_model",
    )
    boundary_row += 1
    gui._add_slider(
        boundary_frame,
        boundary_row,
        "dictation_ai_sentence_finalize_age",
        gui._tr("label.dictation_ai_sentence_finalize_age", "문장 확정 관찰 횟수"),
        dictation_ai_default("sentenceFinalizeAge"),
        1,
        8,
        resolution=1,
        label_key="label.dictation_ai_sentence_finalize_age",
    )
    boundary_row += 1
    stt_boundary_hint_row = boundary_row
    _add_hint(
        gui,
        ttk,
        boundary_frame,
        boundary_row,
        "hint.dictation_ai_sentence_boundary",
        "STT 결과 문장 경계 처리는 STT가 만든 텍스트를 completed/pending 후보로 나누고, 문장 확정 관찰 횟수에 따라 후보를 final로 확정하는 단계입니다. 모든 STT 언어에서 이 backend/model을 사용합니다.",
    )
    gui._dictation_ai_stt_boundary_parent = boundary_frame
    gui._dictation_ai_stt_boundary_rows = [stt_boundary_backend_row, stt_boundary_model_row, stt_boundary_hint_row]

    translation_group, row = _add_group(gui, ttk, tab_whisper, row, "label.dictation_ai_group_translation", "번역")
    translation_row = 0
    gui._add_bool_switch(
        translation_group,
        translation_row,
        "dictation_ai_translation_enabled",
        gui._tr("label.dictation_ai_translation_enabled", "번역 창"),
        dictation_ai_default("translationEnabled"),
        label_key="label.dictation_ai_translation_enabled",
    )
    translation_row += 1
    gui._add_combo(
        translation_group,
        translation_row,
        "dictation_ai_translation_target_language",
        gui._tr("label.dictation_ai_translation_target_language", "번역 대상 언어"),
        dictation_ai_translation_target_options(),
        dictation_ai_translation_target_display_from_raw(dictation_ai_default("translationTargetLanguage")),
        label_key="label.dictation_ai_translation_target_language",
    )
    translation_row += 1
    gui._add_combo(
        translation_group,
        translation_row,
        "dictation_ai_translation_backend",
        gui._tr("label.dictation_ai_translation_backend", "번역 백엔드"),
        dictation_ai_translation_backend_options_for_target(dictation_ai_default("translationTargetLanguage")),
        dictation_ai_default("translationBackend"),
        label_key="label.dictation_ai_translation_backend",
    )
    translation_row += 1

    dictation_ai_translation_frame = ttk.Frame(translation_group)
    dictation_ai_translation_frame.grid(row=translation_row, column=0, columnspan=4, sticky="ew", padx=0, pady=(0, 4))
    dictation_ai_translation_frame.columnconfigure(0, weight=1)
    _add_hint(
        gui,
        ttk,
        dictation_ai_translation_frame,
        0,
        "hint.dictation_ai_translation_builtin_backend",
        "Whisper 내장 번역은 영어 출력만 지원하며 외부 번역 모델 설정을 사용하지 않습니다.",
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
        "dictation_ai_translation_model",
        gui._tr("label.dictation_ai_translation_model", "번역 모델"),
        dictation_ai_translation_model_options(),
        dictation_ai_default("translationModel"),
        label_key="label.dictation_ai_translation_model",
    )
    nllb_row += 1
    gui._add_combo(
        nllb_translation_frame,
        nllb_row,
        "dictation_ai_translation_device",
        gui._tr("label.dictation_ai_translation_device", "번역 장치"),
        ["cuda"],
        dictation_ai_default("translationDevice"),
        label_key="label.dictation_ai_translation_device",
    )
    nllb_row += 1
    gui._add_combo(
        nllb_translation_frame,
        nllb_row,
        "dictation_ai_translation_compute_type",
        gui._tr("label.dictation_ai_translation_compute_type", "번역 연산 타입"),
        ["float16", "float32"],
        dictation_ai_default("translationComputeType"),
        label_key="label.dictation_ai_translation_compute_type",
    )
    nllb_row += 1
    gui._add_slider(
        nllb_translation_frame,
        nllb_row,
        "dictation_ai_translation_beam_size",
        gui._tr("label.dictation_ai_translation_beam_size", "번역 Beam 크기"),
        dictation_ai_default("translationBeamSize"),
        1,
        8,
        resolution=1,
        label_key="label.dictation_ai_translation_beam_size",
    )
    nllb_row += 1
    gui._add_slider(
        nllb_translation_frame,
        nllb_row,
        "dictation_ai_translation_max_new_tokens",
        gui._tr("label.dictation_ai_translation_max_new_tokens", "번역 최대 토큰"),
        dictation_ai_default("translationMaxNewTokens"),
        16,
        512,
        resolution=16,
        label_key="label.dictation_ai_translation_max_new_tokens",
    )
    nllb_row += 1
    _add_hint(
        gui,
        ttk,
        nllb_translation_frame,
        nllb_row,
        "hint.dictation_ai_translation_target_language",
        "외부 번역 모델은 백엔드와 STT 언어에 따라 사용 가능한 대상 언어와 모델이 제한됩니다. 실시간 성능을 위해 CUDA가 필요합니다.",
    )
    gui._dictation_ai_translation_backend_frames = {
        "whisper": dictation_ai_translation_frame,
        "mock": dictation_ai_translation_frame,
        "nllb-transformers": nllb_translation_frame,
        "m2m100-transformers": nllb_translation_frame,
    }


    reset_whisper_btn = ttk.Button(
        tab_whisper,
        text=gui._tr("button.reset_dictation_ai_settings", "받아쓰기 AI 기본값 복원"),
        command=gui._reset_whisper_settings,
    )
    gui._widgets["dictation_ai_reset_button"] = reset_whisper_btn
    gui._register_localized_widget(reset_whisper_btn, "button.reset_dictation_ai_settings", "받아쓰기 AI 기본값 복원")
    reset_whisper_btn.grid(row=row, column=0, columnspan=4, sticky="ew", padx=4, pady=(6, 0))
