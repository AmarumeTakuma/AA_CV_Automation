import tkinter as tk
from tkinter import messagebox

from device_controller import DeviceCommunicationError
from runtime_state import OperationState
from ui_utils import disable_all_widgets_on_error, reset_ui_state, set_operation_state


def attempt_one_time_comm_recovery(state, add_log):
    if state.is_closing:
        return

    if not state.device:
        return

    try:
        # 半断線状態を避けるため、一度ポートを閉じてから再接続を試みる
        if state.device.ser and state.device.ser.is_open:
            state.device.ser.close()
        state.device.is_connected = False

        if not state.device.connect():
            raise DeviceCommunicationError("Auto reconnect failed.")
        if not state.device.initialize_devices():
            raise DeviceCommunicationError("Auto re-initialization failed.")

        reset_ui_state(state)
        try:
            state.status_label.config(text="Recovered from communication error. Ready.")
            add_log("Communication recovered: Auto reconnection successful.")
        except tk.TclError:
            pass

        # Transition back to IDLE on successful recovery
        set_operation_state(state, OperationState.IDLE, add_log)
    except Exception as recover_err:
        print(f"Auto recovery failed: {recover_err}")
        try:
            state.device.close()
        except Exception:
            pass
        state.device.is_connected = False

        try:
            state.status_label.config(text="Disconnected. Please restart the application.")
            add_log("Auto recovery failed: Application restart required.")
        except Exception:
            pass

        try:
            messagebox.showerror(
                "Communication Error",
                f"Auto recovery failed.\n\nDetails: {recover_err}\n\nPlease restart the application.",
            )
        except tk.TclError:
            pass

        disable_all_widgets_on_error(state)
        # Transition to FAULT state on recovery failure
        set_operation_state(state, OperationState.FAULT, add_log)


def handle_device_comm_error(state, context, err, add_log):
    print(f"Device Communication Error in {context}: {err}")
    if state.is_closing:
        return

    if state.operation_state == OperationState.RECOVERING:
        return

    # Transition to RECOVERING state
    set_operation_state(state, OperationState.RECOVERING, add_log)

    if state.device:
        state.device.is_connected = False

    try:
        state.status_label.config(text="Communication error detected. Trying auto recovery once...")
        add_log(f"Communication error detected in {context}. Attempting auto recovery...")
    except Exception:
        pass

    disable_all_widgets_on_error(state)

    for extra in (state.start_btn, state.di1_btn, state.estop_chk):
        if extra:
            try:
                extra.config(state=tk.DISABLED)
            except tk.TclError:
                pass

    current_root = state.root
    if current_root and current_root.winfo_exists():
        try:
            current_root.after(300, lambda: attempt_one_time_comm_recovery(state, add_log))
        except tk.TclError:
            pass
