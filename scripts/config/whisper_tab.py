from __future__ import annotations

from src.domain.whisper_defaults import whisper_default

from scripts.config.whisper_options import (
    whisper_backend_options,
    whisper_language_display_from_raw,
    whisper_language_options,
    whisper_model_options,
    whisper_post_processing_profile_options,
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
        gui._tr("label.whisper_enabled", "Whisper 음성 인식"),
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
        gui._tr("label.whisper_input_device", "입력 장치"),
        whisper_input_display_values,
        whisper_input_default_display,
        label_key="label.whisper_input_device",
    )
    row += 1

    whisper_input_meter_btn = ttk.Button(
        tab_whisper,
        text=gui._tr("button.whisper_input_meter", "Whisper 입력 dB 미터"),
        command=gui._run_whisper_input_meter,
    )
    gui._register_localized_widget(whisper_input_meter_btn, "button.whisper_input_meter", "Whisper 입력 dB 미터")
    whisper_input_meter_btn.grid(row=row, column=0, columnspan=4, sticky="ew", padx=4, pady=(6, 0))
    row += 1

    gui._add_combo(
        tab_whisper,
        row,
        "whisper_backend",
        gui._tr("label.whisper_backend", "Whisper 백엔드"),
        whisper_backend_options(),
        whisper_default("backend"),
        label_key="label.whisper_backend",
    )
    row += 1
    gui._add_combo(
        tab_whisper,
        row,
        "whisper_model",
        gui._tr("label.whisper_model", "Whisper 모델"),
        whisper_model_options(),
        whisper_default("model"),
        label_key="label.whisper_model",
    )
    row += 1
    gui._add_combo(
        tab_whisper,
        row,
        "whisper_language",
        gui._tr("label.whisper_language", "인식 언어(단일 선택)"),
        whisper_language_options(),
        whisper_language_display_from_raw(whisper_default("language")),
        label_key="label.whisper_language",
    )
    row += 1
    row = _add_hint(
        gui,
        ttk,
        tab_whisper,
        row,
        "hint.whisper_language",
        "Whisper는 한 번에 하나의 인식 언어를 사용합니다. 한국어, 영어, 중국어가 섞이면 자동 감지를 사용하세요.",
    )

    stt_frame = ttk.LabelFrame(
        tab_whisper,
        text=gui._tr("label.whisper_stt_models", "언어별 STT 모델"),
    )
    gui._register_localized_widget(stt_frame, "label.whisper_stt_models", "언어별 STT 모델")
    stt_frame.grid(row=row, column=0, columnspan=4, sticky="ew", padx=4, pady=(4, 8))
    for col in range(4):
        stt_frame.columnconfigure(col, weight=1 if col in (1, 3) else 0)
    stt_row = 0
    for lang_code, lang_label in (("en", "영어"), ("ko", "한국어"), ("zh", "중국어")):
        backend_key = f"whisper_stt_backend_{lang_code}"
        model_key = f"whisper_stt_model_{lang_code}"
        backend_default = whisper_default(f"sttBackend{lang_code.title()}")
        model_default = whisper_default(f"sttModel{lang_code.title()}")
        gui._add_combo(
            stt_frame,
            stt_row,
            backend_key,
            gui._tr(f"label.{backend_key}", f"{lang_label} STT 백엔드"),
            whisper_stt_backend_options(),
            backend_default,
            label_key=f"label.{backend_key}",
        )
        stt_row += 1
        gui._add_combo(
            stt_frame,
            stt_row,
            model_key,
            gui._tr(f"label.{model_key}", f"{lang_label} STT 모델"),
            whisper_stt_model_options(backend_default),
            model_default,
            label_key=f"label.{model_key}",
        )
        stt_row += 1
    _add_hint(
        gui,
        ttk,
        stt_frame,
        stt_row,
        "hint.whisper_stt_models",
        "auto-by-language 운영에서는 인식 언어별 STT backend를 사용합니다. 중국어 기본 후보는 FunASR Paraformer이며 실패 시 자동 폴백하지 않습니다.",
    )
    row += 1

    gui._add_combo(
        tab_whisper,
        row,
        "whisper_device",
        gui._tr("label.whisper_device", "STT 장치"),
        ["auto", "cpu", "cuda", "mps"],
        whisper_default("device"),
        label_key="label.whisper_device",
    )
    row += 1
    gui._add_combo(
        tab_whisper,
        row,
        "whisper_compute_type",
        gui._tr("label.whisper_compute_type", "STT 연산 타입"),
        ["auto", "int8", "float16", "float32"],
        whisper_default("computeType"),
        label_key="label.whisper_compute_type",
    )
    row += 1
    gui._add_slider(
        tab_whisper,
        row,
        "whisper_step_seconds",
        gui._tr("label.whisper_step_seconds", "업데이트 간격(초)"),
        whisper_default("stepSeconds"),
        0.5,
        5.0,
        resolution=0.5,
        label_key="label.whisper_step_seconds",
    )
    row += 1
    gui._add_slider(
        tab_whisper,
        row,
        "whisper_window_seconds",
        gui._tr("label.whisper_window_seconds", "컨텍스트 윈도우(초)"),
        whisper_default("windowSeconds"),
        1.0,
        15.0,
        resolution=0.5,
        label_key="label.whisper_window_seconds",
    )
    row += 1
    gui._add_slider(
        tab_whisper,
        row,
        "whisper_commit_lag_seconds",
        gui._tr("label.whisper_commit_lag_seconds", "확정 지연(초)"),
        whisper_default("commitLagSeconds"),
        0.0,
        5.0,
        resolution=0.5,
        label_key="label.whisper_commit_lag_seconds",
    )
    row += 1
    gui._add_slider(
        tab_whisper,
        row,
        "whisper_beam_size",
        gui._tr("label.whisper_beam_size", "Beam 크기"),
        whisper_default("beamSize"),
        1,
        8,
        resolution=1,
        label_key="label.whisper_beam_size",
    )
    row += 1
    gui._add_slider(
        tab_whisper,
        row,
        "whisper_max_new_tokens",
        gui._tr("label.whisper_max_new_tokens", "STT 최대 토큰"),
        whisper_default("maxNewTokens"),
        16,
        512,
        resolution=16,
        label_key="label.whisper_max_new_tokens",
    )
    row += 1
    gui._add_slider(
        tab_whisper,
        row,
        "whisper_temperature",
        gui._tr("label.whisper_temperature", "STT temperature"),
        whisper_default("temperature"),
        0.0,
        1.0,
        resolution=0.1,
        label_key="label.whisper_temperature",
    )
    row += 1
    row = _add_hint(
        gui,
        ttk,
        tab_whisper,
        row,
        "hint.whisper_speed",
        "업데이트 간격을 줄이면 응답성이 좋아집니다. 컨텍스트 윈도우와 확정 지연을 늘리면 보통 STT 정확도와 문장 연속성이 좋아집니다.",
    )

    gui._add_combo(
        tab_whisper,
        row,
        "whisper_post_processing_profile",
        gui._tr("label.whisper_post_processing_profile", "후처리 프로필"),
        whisper_post_processing_profile_options(),
        whisper_default("postProcessingProfile"),
        label_key="label.whisper_post_processing_profile",
    )
    row += 1
    row = _add_hint(
        gui,
        ttk,
        tab_whisper,
        row,
        "hint.whisper_post_processing_profile",
        "auto-by-language는 STT 언어에 따라 후처리 모델을 선택합니다. 영어/한국어는 SaT, 중국어는 FunASR CT-Transformer 구두점 복원을 사용합니다.",
    )

    post_frame = ttk.LabelFrame(
        tab_whisper,
        text=gui._tr("label.whisper_post_processing_models", "언어별 후처리 모델"),
    )
    gui._register_localized_widget(post_frame, "label.whisper_post_processing_models", "언어별 후처리 모델")
    post_frame.grid(row=row, column=0, columnspan=4, sticky="ew", padx=4, pady=(4, 8))
    for col in range(4):
        post_frame.columnconfigure(col, weight=1 if col in (1, 3) else 0)
    post_row = 0
    for lang_code, lang_label in (("en", "영어"), ("ko", "한국어"), ("zh", "중국어")):
        backend_key = f"whisper_sentence_boundary_backend_{lang_code}"
        model_key = f"whisper_sentence_boundary_model_{lang_code}"
        backend_default = whisper_default(f"sentenceBoundaryBackend{lang_code.title()}")
        model_default = whisper_default(f"sentenceBoundaryModel{lang_code.title()}")
        gui._add_combo(
            post_frame,
            post_row,
            backend_key,
            gui._tr(f"label.{backend_key}", f"{lang_label} 백엔드"),
            whisper_sentence_boundary_backend_options(),
            backend_default,
            label_key=f"label.{backend_key}",
        )
        post_row += 1
        gui._add_combo(
            post_frame,
            post_row,
            model_key,
            gui._tr(f"label.{model_key}", f"{lang_label} 모델"),
            whisper_sentence_boundary_model_options(backend_default),
            model_default,
            label_key=f"label.{model_key}",
        )
        post_row += 1
    _add_hint(
        gui,
        ttk,
        post_frame,
        post_row,
        "hint.whisper_post_processing_models",
        "중국어 1차 실험 모델은 FunASR CT-Transformer입니다. funasr 의존성이 필요하며 사용할 수 없으면 Fail-Fast로 중지합니다.",
    )
    row += 1

    gui._add_combo(
        tab_whisper,
        row,
        "whisper_sentence_boundary_backend",
        gui._tr("label.whisper_sentence_boundary_backend", "수동 문장 경계 백엔드"),
        whisper_sentence_boundary_backend_options(),
        whisper_default("sentenceBoundaryBackend"),
        label_key="label.whisper_sentence_boundary_backend",
    )
    row += 1
    gui._add_combo(
        tab_whisper,
        row,
        "whisper_sentence_boundary_model",
        gui._tr("label.whisper_sentence_boundary_model", "수동 문장 경계 모델"),
        whisper_sentence_boundary_model_options(whisper_default("sentenceBoundaryBackend")),
        whisper_default("sentenceBoundaryModel"),
        label_key="label.whisper_sentence_boundary_model",
    )
    row += 1
    row = _add_hint(
        gui,
        ttk,
        tab_whisper,
        row,
        "hint.whisper_sentence_boundary_manual",
        "수동 문장 경계 백엔드/모델은 후처리 프로필이 manual일 때만 사용됩니다.",
    )

    gui._add_bool_switch(
        tab_whisper,
        row,
        "whisper_translation_enabled",
        gui._tr("label.whisper_translation_enabled", "번역 창"),
        whisper_default("translationEnabled"),
        label_key="label.whisper_translation_enabled",
    )
    row += 1
    gui._add_combo(
        tab_whisper,
        row,
        "whisper_translation_backend",
        gui._tr("label.whisper_translation_backend", "번역 백엔드"),
        whisper_translation_backend_options(),
        whisper_default("translationBackend"),
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
        "Whisper 번역은 영어 출력만 지원하며 외부 번역 모델 설정을 사용하지 않습니다.",
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
    row += 1

    reset_whisper_btn = ttk.Button(
        tab_whisper,
        text=gui._tr("button.reset_whisper_settings", "Whisper 기본값 복원"),
        command=gui._reset_whisper_settings,
    )
    gui._register_localized_widget(reset_whisper_btn, "button.reset_whisper_settings", "Whisper 기본값 복원")
    reset_whisper_btn.grid(row=row, column=0, columnspan=4, sticky="ew", padx=4, pady=(6, 0))
