from __future__ import annotations


def build_io_tab(
    gui,
    tab_io,
    ttk,
    system_name,
    discover_cameras,
    discover_camera_mode_options,
    output_backend_options,
    default_virtual_output_device,
) -> None:
    is_macos = system_name() == "Darwin"
    cameras = discover_cameras()
    camera_values = [c["devicePath"] for c in cameras] or (["0"] if is_macos else ["/dev/video0"])

    row = 0
    gui._add_bool_switch(
        tab_io,
        row,
        "camera_server_enabled",
        gui._tr("label.camera_server_enabled", "Camera server"),
        True,
        label_key="label.camera_server_enabled",
    )
    row += 1
    gui._input_device_label = gui._add_combo(
        tab_io,
        row,
        "input_device",
        gui._tr("label.input_device", "Input device"),
        camera_values,
        camera_values[0],
        readonly=True,
        label_key="label.input_device",
    )
    row += 1
    initial_modes = discover_camera_mode_options(camera_values[0]) if camera_values else [(1280, 720, "30")]
    width_values = sorted({str(w) for w, _h, _fps in initial_modes}, key=lambda v: int(v))
    default_w = width_values[0] if width_values else "1280"
    height_values = sorted({str(h) for w, h, _fps in initial_modes if str(w) == default_w}, key=lambda v: int(v))
    default_h = height_values[0] if height_values else "720"
    gui._add_combo(
        tab_io,
        row,
        "input_width",
        gui._tr("label.input_width", "Input width"),
        width_values,
        default_w,
        label_key="label.input_width",
    )
    row += 1
    gui._add_combo(
        tab_io,
        row,
        "input_height",
        gui._tr("label.input_height", "Input height"),
        height_values,
        default_h,
        label_key="label.input_height",
    )
    row += 1
    fps_values = sorted(
        {fps for w, h, fps in initial_modes if str(w) == default_w and str(h) == default_h},
        key=lambda v: float(v),
    ) or ["30"]
    gui._add_combo(
        tab_io,
        row,
        "input_fps",
        gui._tr("label.input_fps", "Input FPS"),
        fps_values,
        "30",
        label_key="label.input_fps",
    )
    row += 1
    gui._add_slider(
        tab_io,
        row,
        "input_software_zoom",
        gui._tr("label.input_sw_zoom", "Input SW zoom"),
        1.0,
        1.0,
        4.0,
        resolution=0.01,
        label_key="label.input_sw_zoom",
    )
    row += 1

    output_backends = output_backend_options()
    gui._add_combo(
        tab_io,
        row,
        "output_backend",
        gui._tr("label.output_backend", "Output backend"),
        output_backends,
        output_backends[0],
        label_key="label.output_backend",
    )
    row += 1
    default_output_device = "virtual-cam" if is_macos else default_virtual_output_device(discover_cameras())
    initial_output_modes = discover_camera_mode_options(default_output_device)
    gui._output_modes = initial_output_modes
    output_width_values = sorted({str(w) for w, _h, _fps in initial_output_modes}, key=lambda v: int(v))
    output_default_w = output_width_values[0] if output_width_values else "1280"
    output_height_values = sorted(
        {str(h) for w, h, _fps in initial_output_modes if str(w) == output_default_w},
        key=lambda v: int(v),
    )
    output_default_h = output_height_values[0] if output_height_values else "720"
    output_fps_values = sorted(
        {
            str(int(round(float(fps))))
            for w, h, fps in initial_output_modes
            if str(w) == output_default_w and str(h) == output_default_h
        },
        key=lambda v: int(v),
    )
    gui._output_device_label = gui._add_text(
        tab_io,
        row,
        "output_device",
        gui._tr("label.output_path", "Output path"),
        default_output_device,
        label_key="label.output_path",
    )
    row += 1
    gui._add_combo(
        tab_io,
        row,
        "output_width",
        gui._tr("label.output_width", "Output width"),
        output_width_values or ["1280"],
        output_default_w,
        label_key="label.output_width",
    )
    row += 1
    gui._add_combo(
        tab_io,
        row,
        "output_height",
        gui._tr("label.output_height", "Output height"),
        output_height_values or ["720"],
        output_default_h,
        label_key="label.output_height",
    )
    row += 1
    gui._add_combo(
        tab_io,
        row,
        "output_fps",
        gui._tr("label.output_fps", "Output FPS"),
        output_fps_values or ["30"],
        output_fps_values[0] if output_fps_values else "30",
        label_key="label.output_fps",
    )
    row += 1
    if system_name() == "Linux":
        create_cam_btn = ttk.Button(
            tab_io,
            text=gui._tr("button.create_virtual_camera", "Create virtual camera"),
            command=gui._create_virtual_camera,
        )
        gui._register_localized_widget(create_cam_btn, "button.create_virtual_camera", "Create virtual camera")
        remove_cam_btn = ttk.Button(
            tab_io,
            text=gui._tr("button.remove_virtual_camera", "Remove virtual camera"),
            command=gui._remove_virtual_camera,
        )
        gui._register_localized_widget(remove_cam_btn, "button.remove_virtual_camera", "Remove virtual camera")
        create_cam_btn.grid(row=row, column=0, columnspan=2, sticky="ew", padx=4, pady=(6, 0))
        remove_cam_btn.grid(row=row, column=2, columnspan=2, sticky="ew", padx=4, pady=(6, 0))
        row += 1
    reset_io_btn = ttk.Button(
        tab_io,
        text=gui._tr("button.reset_io_settings", "Restore IO defaults"),
        command=gui._reset_io_settings,
    )
    gui._register_localized_widget(reset_io_btn, "button.reset_io_settings", "Restore IO defaults")
    reset_io_btn.grid(row=row, column=0, columnspan=4, sticky="ew", padx=4, pady=(6, 0))
