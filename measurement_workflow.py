import tkinter as tk
from tkinter import messagebox

from device_controller import DeviceCommunicationError, DeviceTimeoutError
from measurement_prestart_automation import show_start_dialog
from stationkit_measurement_controller import MeasurementExecuteRequest
from runtime_state import OperationState
from ui_utils import reset_ui_state, set_operation_state, can_start_measurement
# ▼ 追加：新しく作ったファイルから、最前面化の機能をインポート
from system_actions import bring_window_to_front


def finish_measurement_handler(state, add_log):
    if state.is_closing:
        return

    try:
        # Use stationkit controller API instead of direct device call
        if state.stationkit_controller:
            try:
                state.stationkit_controller.stop_measurement()
            except Exception:
                # Fallback to direct device call if controller stop fails
                state.device.stop_measurement()
        else:
            state.device.stop_measurement()
    except Exception as err:
        print(f"Error in finish_measurement_handler: {err}")
    finally:
        if state.current_measurement and state.current_measurement.status == "running":
            state.current_measurement.mark_completed()
            add_log(
                f"Measurement completed: {state.current_measurement.target_cell} "
                f"({state.current_measurement.save_dir}/{state.current_measurement.filename})"
            )
        
        # Transition back to IDLE
        set_operation_state(state, OperationState.IDLE, add_log)
        reset_ui_state(state)

        # 測定が正常終了したらアプリを最前面に出す
        bring_window_to_front(state)

        try:
            state.status_label.config(text="Measurement COMPLETED.")
        except tk.TclError:
            pass


def execute_start_measurement(state, filename, save_dir, target_cell, add_log, handle_device_comm_error):
    if not can_start_measurement(state):
        return

    try:
        state.stationkit_controller.execute(
            MeasurementExecuteRequest(
                filename=filename,
                save_dir=save_dir,
                target_cell=target_cell,
            )
        )
    except DeviceCommunicationError as err:
        set_operation_state(state, OperationState.IDLE, add_log)
        handle_device_comm_error("execute_start_measurement", err)
    except DeviceTimeoutError as err:
        print(f"Device Timeout in execute_start_measurement: {err}")
        set_operation_state(state, OperationState.IDLE, add_log)
        if not state.is_closing:
            messagebox.showerror("Device Error", str(err))
    except Exception as err:
        print(f"Error in execute_start_measurement: {err}")
        set_operation_state(state, OperationState.IDLE, add_log)


def on_start(state, add_log, handle_device_comm_error):
    if not state.device.is_connected or state.is_closing:
        return
    if state.config.di1_output_pin < 0:
        messagebox.showinfo("Info", "DI1 Output Pin Disabled")
        return

    show_start_dialog(state, add_log, handle_device_comm_error, execute_start_measurement)