from __future__ import annotations


def build_face_tab(gui, tab_face, ttk) -> None:
    row = 0
    gui._add_bool_switch(
        tab_face,
        row,
        "face_enhance_enabled",
        gui._tr("label.face_enhance_enabled", "Face quality enhancement"),
        False,
        label_key="label.face_enhance_enabled",
    )
    row += 1
    gui._add_bool_switch(
        tab_face,
        row,
        "face_deidentify_enabled",
        gui._tr("label.face_deidentify_enabled", "Face deidentify (eye mask)"),
        False,
        label_key="label.face_deidentify_enabled",
    )
    row += 1
    gui._add_slider(
        tab_face,
        row,
        "face_enhance_gamma",
        gui._tr("label.face_enhance_gamma", "Face gamma"),
        1.0,
        0.5,
        1.8,
        resolution=0.01,
        label_key="label.face_enhance_gamma",
    )
    row += 1
    gui._add_slider(
        tab_face,
        row,
        "face_enhance_brightness",
        gui._tr("label.face_enhance_brightness", "Face brightness"),
        0.0,
        -80.0,
        80.0,
        resolution=1,
        label_key="label.face_enhance_brightness",
    )
    row += 1
    gui._add_slider(
        tab_face,
        row,
        "face_enhance_saturation",
        gui._tr("label.face_enhance_saturation", "Face saturation"),
        1.0,
        0.5,
        1.8,
        resolution=0.01,
        label_key="label.face_enhance_saturation",
    )
    row += 1
    gui._add_slider(
        tab_face,
        row,
        "face_enhance_blend",
        gui._tr("label.face_enhance_blend", "Face enhancement strength"),
        0.65,
        0.0,
        1.0,
        resolution=0.01,
        label_key="label.face_enhance_blend",
    )
    row += 1
    gui._add_slider(
        tab_face,
        row,
        "face_enhance_min_size_ratio",
        gui._tr("label.face_enhance_min_size_ratio", "Minimum face size ratio"),
        0.12,
        0.05,
        0.50,
        resolution=0.01,
        label_key="label.face_enhance_min_size_ratio",
    )
    row += 1
    gui._add_slider(
        tab_face,
        row,
        "face_enhance_edge_dither",
        gui._tr("label.face_enhance_edge_dither", "Face edge dither"),
        0.25,
        0.0,
        1.0,
        resolution=0.01,
        label_key="label.face_enhance_edge_dither",
    )
    row += 1
    reset_face_btn = ttk.Button(
        tab_face,
        text=gui._tr("button.reset_face_settings", "Restore face quality defaults"),
        command=gui._reset_face_settings,
    )
    gui._register_localized_widget(reset_face_btn, "button.reset_face_settings", "Restore face quality defaults")
    reset_face_btn.grid(row=row, column=0, columnspan=4, sticky="ew", padx=4, pady=(6, 0))
