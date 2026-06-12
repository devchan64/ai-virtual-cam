from __future__ import annotations


def build_audio_tab(
    gui,
    tab_audio,
    ttk,
    system_name,
    audio_input_device_candidates,
    audio_default_input_device,
    audio_output_device_candidates,
    audio_default_output_device,
    audio_device_display_values,
    audio_denoise_backend_options,
) -> None:
    row = 0
    gui._add_bool_switch(tab_audio, row, "audio_enabled", gui._tr("label.audio_enabled", "Audio mixer"), True, label_key="label.audio_enabled")
    row += 1

    audio_input_candidates = audio_input_device_candidates()
    audio_input_default = audio_default_input_device()
    if audio_input_default not in audio_input_candidates:
        audio_input_candidates.append(audio_input_default)
    audio_input_display_values, gui._audio_input_display_to_raw = audio_device_display_values("input", audio_input_candidates)
    audio_input_default_display = next(
        (k for k, v in gui._audio_input_display_to_raw.items() if v == audio_input_default),
        audio_input_default,
    )
    gui._add_combo(tab_audio, row, "audio_input_device", gui._tr("label.audio_input_device", "Input device"), audio_input_display_values, audio_input_default_display, label_key="label.audio_input_device")
    row += 1
    mic_input_meter_btn = ttk.Button(tab_audio, text=gui._tr("button.audio_input_meter", "Input dB meter"), command=gui._run_audio_input_meter)
    gui._register_localized_widget(mic_input_meter_btn, "button.audio_input_meter", "Input dB meter")
    mic_input_meter_btn.grid(row=row, column=0, columnspan=4, sticky="ew", padx=4, pady=(6, 0))
    row += 1

    audio_output_candidates = audio_output_device_candidates()
    audio_output_default = audio_default_output_device()
    if audio_output_default not in audio_output_candidates:
        audio_output_candidates.append(audio_output_default)
    audio_output_display_values, gui._audio_output_display_to_raw = audio_device_display_values("output", audio_output_candidates)
    audio_output_default_display = next(
        (k for k, v in gui._audio_output_display_to_raw.items() if v == audio_output_default),
        audio_output_default,
    )
    gui._add_combo(tab_audio, row, "audio_output_device", gui._tr("label.audio_output_device", "Output device"), audio_output_display_values, audio_output_default_display, label_key="label.audio_output_device")
    row += 1

    if system_name() == "Linux":
        create_mic_btn = ttk.Button(tab_audio, text=gui._tr("button.create_virtual_mic", "Create virtual microphone"), command=gui._create_virtual_speaker)
        gui._register_localized_widget(create_mic_btn, "button.create_virtual_mic", "Create virtual microphone")
        remove_mic_btn = ttk.Button(tab_audio, text=gui._tr("button.remove_virtual_mic", "Remove virtual microphone"), command=gui._remove_virtual_speaker)
        gui._register_localized_widget(remove_mic_btn, "button.remove_virtual_mic", "Remove virtual microphone")
        create_mic_btn.grid(row=row, column=0, columnspan=2, sticky="ew", padx=4, pady=(6, 0))
        remove_mic_btn.grid(row=row, column=2, columnspan=2, sticky="ew", padx=4, pady=(6, 0))
        row += 1

    gui._add_int(tab_audio, row, "audio_sample_rate", gui._tr("label.audio_sample_rate", "Sample rate"), 48000, label_key="label.audio_sample_rate")
    gui._add_int(tab_audio, row, "audio_channels", gui._tr("label.audio_channels", "Channels"), 1, col_offset=2, label_key="label.audio_channels")
    row += 1
    gui._add_int(tab_audio, row, "audio_frame_ms", gui._tr("label.audio_frame_ms", "Frame ms"), 20, label_key="label.audio_frame_ms")
    row += 1
    gui._add_bool_switch(tab_audio, row, "audio_denoise_enabled", gui._tr("label.audio_denoise_enabled", "Noise cancel"), True, label_key="label.audio_denoise_enabled")
    row += 1
    denoise_backends = audio_denoise_backend_options()
    gui._add_combo(tab_audio, row, "audio_denoise_backend", gui._tr("label.audio_denoise_backend", "NC backend"), denoise_backends, denoise_backends[0], label_key="label.audio_denoise_backend")
    row += 1

    sliders = [
        ("audio_denoise_strength", "label.audio_denoise_strength", "NC strength", 0.50, 0.0, 1.0, 0.01),
        ("audio_gate_threshold_db", "label.audio_gate_threshold_db", "Gate threshold dB", -40.0, -80.0, 0.0, 0.5),
        ("audio_gate_hysteresis_db", "label.audio_gate_hysteresis_db", "Gate hysteresis dB", 4.0, 0.0, 20.0, 0.5),
        ("audio_gate_min_voice_band_ratio", "label.audio_gate_min_voice_band_ratio", "Min voice band ratio", 0.50, 0.0, 1.0, 0.01),
        ("audio_gate_attack_ms", "label.audio_gate_attack_ms", "Gate attack ms", 30, 0, 500, 1),
        ("audio_gate_hold_ms", "label.audio_gate_hold_ms", "Gate hold ms", 160, 0, 2000, 1),
        ("audio_gate_release_ms", "label.audio_gate_release_ms", "Gate release ms", 2000, 0, 4000, 1),
        ("audio_gate_open_gain", "label.audio_gate_open_gain", "Gate open gain", 1.0, 0.0, 2.0, 0.01),
        ("audio_gate_closed_gain", "label.audio_gate_closed_gain", "Gate closed gain", 0.0, 0.0, 1.0, 0.01),
    ]
    for key, label_key, default_label, default, min_value, max_value, resolution in sliders:
        gui._add_slider(tab_audio, row, key, gui._tr(label_key, default_label), default, min_value, max_value, resolution=resolution, label_key=label_key)
        row += 1

    auto_tune_btn = ttk.Button(tab_audio, text=gui._tr("button.auto_tune_audio_gate", "Auto tune audio gate"), command=gui._auto_tune_audio_gate)
    gui._register_localized_widget(auto_tune_btn, "button.auto_tune_audio_gate", "Auto tune audio gate")
    auto_tune_btn.grid(row=row, column=0, columnspan=2, sticky="ew", padx=4, pady=(6, 0))
    test_gate_btn = ttk.Button(tab_audio, text=gui._tr("button.run_audio_gate_test", "Audio gate test"), command=gui._run_audio_gate_test)
    gui._register_localized_widget(test_gate_btn, "button.run_audio_gate_test", "Audio gate test")
    test_gate_btn.grid(row=row, column=2, columnspan=2, sticky="ew", padx=4, pady=(6, 0))
    row += 1
    reset_audio_btn = ttk.Button(tab_audio, text=gui._tr("button.reset_audio_settings", "Restore audio defaults"), command=gui._reset_audio_settings)
    gui._register_localized_widget(reset_audio_btn, "button.reset_audio_settings", "Restore audio defaults")
    reset_audio_btn.grid(row=row, column=0, columnspan=4, sticky="ew", padx=4, pady=(6, 0))
