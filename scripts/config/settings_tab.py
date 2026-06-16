from __future__ import annotations


def build_settings_tab(gui, tab_settings, ttk) -> None:
    row = 0

    settings_frame = ttk.LabelFrame(
        tab_settings,
        text=gui._tr("label.settings_json_group", "Settings JSON"),
    )
    gui._register_localized_widget(settings_frame, "label.settings_json_group", "Settings JSON")
    settings_frame.grid(row=row, column=0, columnspan=4, sticky="ew", padx=4, pady=(0, 8))
    settings_frame.columnconfigure(0, weight=1)
    row += 1

    reset_btn = ttk.Button(
        settings_frame,
        text=gui._tr("button.reset_settings_json", "Reset settings JSON"),
        command=gui._reset_settings_json,
    )
    gui._register_localized_widget(reset_btn, "button.reset_settings_json", "Reset settings JSON")
    reset_btn.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
