import datetime
import tkinter as tk

from runtime_state import OperationState


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


def set_operation_state(state, new_state, add_log_func=None):
    """Set new operation state and log transition."""
    old_state = state.operation_state
    state.operation_state = new_state
    if add_log_func:
        add_log_func(f"[STATE] {old_state.value} -> {new_state.value}")


def is_state_allowed(state, required_state):
    """Check if operation is allowed in current state."""
    if isinstance(required_state, list):
        return state.operation_state in required_state
    else:
        return state.operation_state == required_state


def can_start_measurement(state):
    """Check if measurement can be started (only in IDLE state with device connected)."""
    return (
        state.operation_state == OperationState.IDLE
        and state.device
        and state.device.is_connected
        and not state.is_closing
    )


def can_estop(state):
    """Check if E-STOP can be triggered (allowed from IDLE or MEASURING with device connected)."""
    return (
        state.operation_state in (OperationState.IDLE, OperationState.MEASURING)
        and state.device
        and state.device.is_connected
        and not state.is_closing
    )


def can_interact(state):
    """Check if user can interact (only in IDLE state with device connected)."""
    return (
        state.operation_state == OperationState.IDLE
        and state.device
        and state.device.is_connected
        and not state.is_closing
    )


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
