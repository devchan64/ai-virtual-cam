from __future__ import annotations

def slider_decimal_places(step: float) -> int:
    step = abs(float(step or 1))
    if step >= 1:
        return 0
    text = f"{step:.10f}".rstrip("0")
    if "." not in text:
        return 0
    return len(text.split(".", 1)[1])


def snap_slider_value(value: float, min_value: float, max_value: float, step: float) -> float:
    minimum = float(min_value)
    maximum = float(max_value)
    normalized_step = abs(float(step or 0))
    raw = max(minimum, min(maximum, float(value)))
    if normalized_step <= 0:
        return raw
    steps = round((raw - minimum) / normalized_step)
    snapped = minimum + steps * normalized_step
    snapped = max(minimum, min(maximum, snapped))
    decimals = max(slider_decimal_places(normalized_step), slider_decimal_places(minimum), slider_decimal_places(maximum))
    return round(snapped, decimals)


def format_slider_value(value: float, step: float) -> str:
    decimals = slider_decimal_places(step)
    if decimals == 0:
        return str(int(round(float(value))))
    return f"{float(value):.{decimals}f}"


def add_numeric_slider(
    gui,
    parent,
    row,
    key: str,
    label: str,
    default,
    min_value,
    max_value,
    *,
    step=0.01,
    label_key: str | None = None,
):
    tk = gui._tk
    ttk = gui._ttk
    minimum = float(min_value)
    maximum = float(max_value)
    normalized_step = abs(float(step or 0.01))
    initial = snap_slider_value(float(default), minimum, maximum, normalized_step)

    label_text = gui._tr(label_key or label, label)
    label_widget = ttk.Label(parent, text=label_text)
    if label_key is not None:
        gui._register_localized_widget(label_widget, label_key, label)
    label_widget.grid(row=row, column=0, sticky="w")

    var = tk.DoubleVar(value=initial)
    entry_var = tk.StringVar(value=format_slider_value(initial, normalized_step))
    gui.vars[key] = var

    updating = {"active": False}

    def normalize(value) -> float:
        return snap_slider_value(float(value), minimum, maximum, normalized_step)

    def apply_value(value, *, update_var: bool = True) -> float:
        snapped = normalize(value)
        updating["active"] = True
        try:
            if update_var:
                var.set(snapped)
            entry_var.set(format_slider_value(snapped, normalized_step))
        finally:
            updating["active"] = False
        return snapped

    def on_scale_change(raw):
        if updating["active"]:
            return
        apply_value(raw)

    scale = ttk.Scale(parent, from_=minimum, to=maximum, variable=var, command=on_scale_change)

    def on_scale_release(_event=None):
        apply_value(var.get())

    def on_click(event):
        width = max(1, event.widget.winfo_width())
        ratio = max(0.0, min(1.0, float(event.x) / float(width)))
        value = minimum + ratio * (maximum - minimum)
        apply_value(value)
        return "break"

    def commit_entry(_event=None):
        try:
            apply_value(entry_var.get())
        except (TypeError, ValueError):
            apply_value(var.get())
        return "break"

    def step_entry(delta: int):
        apply_value(var.get() + delta * normalized_step)
        return "break"

    scale.bind("<Button-1>", on_click)
    scale.bind("<ButtonRelease-1>", on_scale_release)
    scale.grid(row=row, column=1, columnspan=2, sticky="ew", padx=4)

    entry = ttk.Entry(parent, textvariable=entry_var, width=8, justify="right")
    entry.grid(row=row, column=3, sticky="e", padx=(4, 0))
    entry.bind("<Return>", commit_entry)
    entry.bind("<KP_Enter>", commit_entry)
    entry.bind("<FocusOut>", commit_entry)
    entry.bind("<Up>", lambda _event: step_entry(1))
    entry.bind("<Down>", lambda _event: step_entry(-1))

    gui._slider_value_vars[key] = entry_var
    gui._slider_formatters[key] = lambda value: format_slider_value(snap_slider_value(value, minimum, maximum, normalized_step), normalized_step)
    gui._slider_normalizers[key] = normalize
    gui._widgets[key] = scale
    gui._slider_entries[key] = entry
    return label_widget
