from __future__ import annotations


def build_background_tab(gui, tab_bg, ttk) -> None:
    row = 0
    gui._add_bool_switch(
        tab_bg,
        row,
        "bg_enabled",
        gui._tr("label.bg_enabled", "Background"),
        True,
        label_key="label.bg_enabled",
    )
    row += 1
    gui._add_combo(
        tab_bg,
        row,
        "bg_mode",
        gui._tr("label.bg_mode", "Background mode"),
        ["chroma", "image", "image_chroma"],
        "chroma",
        label_key="label.bg_mode",
    )
    row += 1
    gui._add_text(
        tab_bg,
        row,
        "bg_image",
        gui._tr("label.bg_image", "Background image"),
        "",
        label_key="label.bg_image",
    )
    browse_bg_image_btn = ttk.Button(
        tab_bg,
        text=gui._tr("button.browse", "Browse"),
        command=gui._pick_bg_image,
    )
    gui._register_localized_widget(browse_bg_image_btn, "button.browse", "Browse")
    browse_bg_image_btn.grid(row=row, column=2, sticky="ew", padx=4)
    row += 1
    gui._add_int(
        tab_bg,
        row,
        "bg_r",
        gui._tr("label.bg_chroma_r", "Chroma R"),
        0,
        label_key="label.bg_chroma_r",
    )
    gui._add_int(
        tab_bg,
        row,
        "bg_g",
        gui._tr("label.bg_chroma_g", "Chroma G"),
        0,
        col_offset=2,
        label_key="label.bg_chroma_g",
    )
    row += 1
    gui._add_int(
        tab_bg,
        row,
        "bg_b",
        gui._tr("label.bg_chroma_b", "Chroma B"),
        0,
        label_key="label.bg_chroma_b",
    )
    pick_color_btn = ttk.Button(
        tab_bg,
        text=gui._tr("button.pick_color", "Pick Color"),
        command=gui._pick_chroma_color,
    )
    gui._register_localized_widget(pick_color_btn, "button.pick_color", "Pick Color")
    pick_color_btn.grid(row=row, column=2, sticky="ew", padx=4)
    row += 1
    gui._add_slider(
        tab_bg,
        row,
        "bg_blend_alpha",
        gui._tr("label.bg_blend_alpha", "Color blend alpha"),
        0.35,
        0.0,
        1.0,
        resolution=0.01,
        label_key="label.bg_blend_alpha",
    )
    row += 1
    reset_bg_btn = ttk.Button(
        tab_bg,
        text=gui._tr("button.reset_background_settings", "Restore background defaults"),
        command=gui._reset_bg_settings,
    )
    gui._register_localized_widget(reset_bg_btn, "button.reset_background_settings", "Restore background defaults")
    reset_bg_btn.grid(row=row, column=0, columnspan=4, sticky="ew", padx=4, pady=(6, 0))
