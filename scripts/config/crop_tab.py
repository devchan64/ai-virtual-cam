from __future__ import annotations


def build_crop_tab(gui, tab_crop, ttk) -> None:
    row = 0
    gui._add_bool_switch(
        tab_crop,
        row,
        "crop_enabled",
        gui._tr("label.crop_enabled", "Framing"),
        True,
        label_key="label.crop_enabled",
    )
    row += 1
    sliders = [
        ("crop_margin", "label.crop_margin", "Person crop margin", 0.25, 0.0, 2.0, 0.01),
        ("crop_pan_smoothing", "label.crop_pan_smoothing", "Pan smoothing", 0.85, 0.0, 1.0, 0.01),
        ("crop_tilt_smoothing", "label.crop_tilt_smoothing", "Tilt smoothing", 0.85, 0.0, 1.0, 0.01),
        ("crop_zoom_smoothing", "label.crop_zoom_smoothing", "Zoom smoothing", 0.80, 0.0, 1.0, 0.01),
        ("crop_upper_body_bias", "label.crop_upper_body_bias", "Upper body bias", 0.00, 0.0, 1.0, 0.01),
        ("crop_upper_body_ratio", "label.crop_upper_body_ratio", "Upper body ratio", 0.60, 0.2, 1.0, 0.01),
        ("crop_upper_body_edge_smoothing", "label.crop_upper_body_edge_smoothing", "Upper body edge smoothing", 0.35, 0.0, 1.0, 0.01),
        ("crop_pan_pid_kp", "label.crop_pan_pid_kp", "Pan PID Kp", 0.35, 0.0, 2.0, 0.01),
        ("crop_pan_pid_ki", "label.crop_pan_pid_ki", "Pan PID Ki", 0.01, 0.0, 0.5, 0.001),
        ("crop_pan_pid_kd", "label.crop_pan_pid_kd", "Pan PID Kd", 0.12, 0.0, 2.0, 0.01),
        ("crop_tilt_pid_kp", "label.crop_tilt_pid_kp", "Tilt PID Kp", 0.35, 0.0, 2.0, 0.01),
        ("crop_tilt_pid_ki", "label.crop_tilt_pid_ki", "Tilt PID Ki", 0.01, 0.0, 0.5, 0.001),
        ("crop_tilt_pid_kd", "label.crop_tilt_pid_kd", "Tilt PID Kd", 0.12, 0.0, 2.0, 0.01),
        ("crop_pan_target_offset_x", "label.crop_pan_target_offset_x", "Pan target offset X", 0.00, -1.0, 1.0, 0.01),
        ("crop_pan_target_offset_y", "label.crop_pan_target_offset_y", "Pan target offset Y", 0.00, -1.0, 1.0, 0.01),
    ]
    for row_offset, (key, label_key, default_label, default, min_value, max_value, resolution) in enumerate(sliders):
        gui._add_slider(
            tab_crop,
            row + row_offset,
            key,
            gui._tr(label_key, default_label),
            default,
            min_value,
            max_value,
            resolution=resolution,
            label_key=label_key,
        )
    row += len(sliders)
    reset_crop_btn = ttk.Button(
        tab_crop,
        text=gui._tr("button.reset_crop_settings", "Restore framing defaults"),
        command=gui._reset_crop_settings,
    )
    gui._register_localized_widget(reset_crop_btn, "button.reset_crop_settings", "Restore framing defaults")
    reset_crop_btn.grid(row=row, column=0, columnspan=4, sticky="ew", padx=4, pady=(6, 0))
