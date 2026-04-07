import datetime
import tkinter as tk


def add_log(state, message):
    """Add a timestamped log entry to the log history combobox."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)

    combo = state.log_combo
    if not combo:
        return

    try:
        if not combo.winfo_exists():
            return
        logs = list(combo["values"])
        logs.insert(0, line)
        combo["values"] = logs
        combo.current(0)
    except tk.TclError:
        pass


def init_gui_vars(state):
    for var in state.elec_chk_vars.values():
        var.set(0)
    for var in state.master_chk_vars.values():
        var.set(0)
    for var in state.gas_chk_vars.values():
        var.set(0)


def toggle_ui_lock(state, is_locked):
    if state.is_closing:
        return

    allowed = [state.estop_chk]
    try:
        for widget in state.all_widgets:
            if not hasattr(widget, "config"):
                continue
            if widget in allowed:
                continue
            widget.config(state=tk.DISABLED if is_locked else tk.NORMAL)
    except tk.TclError:
        pass


def reset_ui_state(state):
    if state.is_closing:
        return

    try:
        toggle_ui_lock(state, False)
        if state.start_btn:
            state.start_btn.config(relief=tk.RAISED)
    except tk.TclError:
        pass


def disable_all_widgets_on_error(state):
    if state.is_closing:
        return

    exit_btn = state.btn_exit

    for widget in state.all_widgets:
        if widget is exit_btn:
            continue
        if hasattr(widget, "config"):
            try:
                widget.config(state=tk.DISABLED)
            except tk.TclError:
                pass

    if exit_btn and hasattr(exit_btn, "config"):
        try:
            exit_btn.config(state=tk.NORMAL)
        except tk.TclError:
            pass
