from __future__ import annotations


def build_segmentation_tab(gui, tab_seg, ttk, segmentation_backend_options) -> None:
    row = 0
    gui._add_combo(
        tab_seg,
        row,
        "seg_backend",
        gui._tr("label.seg_backend", "Seg backend"),
        segmentation_backend_options(),
        "selfie",
        label_key="label.seg_backend",
    )
    row += 1
    gui._add_slider(tab_seg, row, "seg_threshold", gui._tr("label.seg_threshold", "Seg threshold"), 0.65, 0.0, 1.0, resolution=0.01, label_key="label.seg_threshold")
    row += 1
    gui._add_slider(tab_seg, row, "seg_edge_smoothness", gui._tr("label.seg_edge_smoothness", "Edge smoothness"), 0.50, 0.0, 1.0, resolution=0.01, label_key="label.seg_edge_smoothness")
    row += 1
    gui._add_slider(tab_seg, row, "seg_blend_feather", gui._tr("label.seg_blend_feather", "Blend feather"), 0.35, 0.0, 1.0, resolution=0.01, label_key="label.seg_blend_feather")
    row += 1
    gui._add_slider(tab_seg, row, "seg_selfie_model", gui._tr("label.seg_selfie_model", "Selfie model selection"), 1, 0, 1, resolution=1, label_key="label.seg_selfie_model")
    row += 1
    gui._add_slider(tab_seg, row, "seg_selfie_smoothing", gui._tr("label.seg_selfie_smoothing", "Selfie temporal smoothing"), 0.25, 0.0, 0.95, resolution=0.01, label_key="label.seg_selfie_smoothing")
    row += 1
    seg_engine_label = ttk.Label(tab_seg, text=gui._tr("label.engine_options", "Engine options"))
    gui._register_localized_widget(seg_engine_label, "label.engine_options", "Engine options")
    seg_engine_label.grid(row=row, column=0, sticky="w", padx=4, pady=(8, 0))
    row += 1
    gui._add_slider(tab_seg, row, "seg_opt_model_blend", gui._tr("label.seg_opt_model_blend", "Model blend"), 0.60, 0.0, 1.0, resolution=0.01, label_key="label.seg_opt_model_blend")
    row += 1
    gui._add_slider(tab_seg, row, "seg_opt_temporal_alpha", gui._tr("label.seg_opt_temporal_alpha", "Temporal alpha override"), 0.55, 0.0, 0.95, resolution=0.01, label_key="label.seg_opt_temporal_alpha")
    row += 1
    gui._add_slider(tab_seg, row, "seg_opt_mask_blur", gui._tr("label.seg_opt_mask_blur", "Mask blur kernel"), 5, 0, 21, resolution=1, label_key="label.seg_opt_mask_blur")
    row += 1
    gui._add_slider(tab_seg, row, "seg_opt_morph_open", gui._tr("label.seg_opt_morph_open", "Morph open kernel"), 3, 0, 15, resolution=1, label_key="label.seg_opt_morph_open")
    row += 1
    gui._add_slider(tab_seg, row, "seg_opt_morph_close", gui._tr("label.seg_opt_morph_close", "Morph close kernel"), 5, 0, 15, resolution=1, label_key="label.seg_opt_morph_close")
    row += 1
    gui._add_slider(tab_seg, row, "seg_opt_mask_gamma", gui._tr("label.seg_opt_mask_gamma", "Mask gamma"), 0.90, 0.5, 1.5, resolution=0.01, label_key="label.seg_opt_mask_gamma")
    row += 1
    gui._add_text(tab_seg, row, "seg_opt_engine_path", gui._tr("label.seg_opt_engine_path", "TensorRT engine path"), "", label_key="label.seg_opt_engine_path")
    row += 1
    seg_engine_hint = ttk.Label(
        tab_seg,
        text=gui._tr("hint.seg_engine_options", "Available options are limited by selected engine."),
        foreground="#666",
    )
    seg_engine_hint.grid(row=row, column=0, columnspan=4, sticky="w", padx=4, pady=(2, 0))
    gui._register_localized_widget(seg_engine_hint, "hint.seg_engine_options", "Available options are limited by selected engine.")
    row += 1
    reset_seg_btn = ttk.Button(
        tab_seg,
        text=gui._tr("button.reset_segmentation_settings", "Restore segmentation defaults"),
        command=gui._reset_seg_settings,
    )
    gui._register_localized_widget(reset_seg_btn, "button.reset_segmentation_settings", "Restore segmentation defaults")
    reset_seg_btn.grid(row=row, column=0, columnspan=4, sticky="ew", padx=4, pady=(6, 0))
