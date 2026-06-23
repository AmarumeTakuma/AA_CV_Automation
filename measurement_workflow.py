import datetime
import time
import tkinter as tk
from tkinter import messagebox

from device_controller import DeviceCommunicationError, DeviceTimeoutError
from measurement_prestart_automation import show_start_dialog
from stationkit_measurement_controller import MeasurementExecuteRequest
from runtime_state import OperationState
from ui_utils import init_gui_vars, reset_ui_state, toggle_ui_lock, set_operation_state, can_start_measurement, can_estop


def bring_window_to_front(state):
    """Windowsの制限を突破してアプリを確実に最前面へ引きずり出す関数"""
    try:
        if state.root.winfo_exists():
            # 1. 強制的に「常に最前面」属性を付与して画面を奪い取る
            state.root.attributes('-topmost', True)
            state.root.update()
            
            # 2. すぐに「常に最前面」を解除する（これがないと他のアプリが一生前に出られなくなる）
            state.root.attributes('-topmost', False)
            
            # 3. 念押しでOSにフォーカスを要求
            state.root.lift()
            state.root.focus_force()
    except tk.TclError:
        pass

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

        # ▼ 追加：測定が正常終了したらアプリを最前面に出す
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


def on_estop(state, add_log, handle_device_comm_error):
    if not can_estop(state):
        state.estop_var.set(0)
        return
    if state.config.estop_pin < 0:
        state.estop_var.set(0)
        reset_ui_state(state)
        return

    # Transition to ESTOP_PENDING
    set_operation_state(state, OperationState.ESTOP_PENDING, add_log)

    # ▼ 追加：異常事態なので、何が何でもアプリを最前面に叩き出す
    bring_window_to_front(state)

    # ▼▼▼ 追加：サブダイアログ（設定ウィンドウ）が開いていたら強制的に消し飛ばす ▼▼▼
    if hasattr(state, 'active_dialog') and state.active_dialog:
        try:
            if state.active_dialog.winfo_exists():
                state.active_dialog.destroy()
                add_log("Start dialog closed forcefully by E-STOP.")
        except Exception:
            pass
        state.active_dialog = None
    # ▲▲▲ 追加ここまで ▲▲▲

    try:
        if state.estop_var.get():
            state.estop_chk.config(bg="red", fg="white", relief=tk.SUNKEN)
            state.status_label.config(text="E-STOP ACTIVATED!")
            state.root.update()

            print("!!! EMERGENCY STOP ACTIVATED !!!")
            add_log("E-STOP activated.")

            # ▼▼▼ 追加：ハードウェアを安全にシャットダウン ▼▼▼
            if hasattr(state, "stationkit_controller"):
                state.stationkit_controller.force_hardware_all_off()
            # ▲▲▲ 追加ここまで ▲▲▲
            
            state.device.trigger_estop()

            reset_ui_state(state)
            init_gui_vars(state)

            def reset_estop_button_color():
                try:
                    if state.root.winfo_exists():
                        state.estop_chk.config(bg="#ffcccc", fg="black", relief=tk.RAISED)
                        state.estop_var.set(0)
                        state.status_label.config(text="E-STOP Released.")
                        add_log("E-STOP released. System reset.")
                        # Transition back to IDLE
                        set_operation_state(state, OperationState.IDLE, add_log)
                except tk.TclError:
                    pass

            state.root.after(int(state.estop_pulse_duration_sec * 1000), reset_estop_button_color)
            state.last_estop_time = time.monotonic()
        else:
            state.device.set_digital(state.config.estop_pin, 1)
    except DeviceCommunicationError as err:
        set_operation_state(state, OperationState.IDLE, add_log)
        handle_device_comm_error("on_estop", err)
    except DeviceTimeoutError as err:
        print(f"Device Timeout in on_estop: {err}")
        set_operation_state(state, OperationState.IDLE, add_log)
        if not state.is_closing:
            messagebox.showerror("Device Error", str(err))
    except Exception as err:
        print(f"Error in on_estop: {err}")
        set_operation_state(state, OperationState.IDLE, add_log)


def on_init_btn(state, add_log, handle_device_comm_error):
    print("Manual initialization requested.")
    add_log("Manual initialization requested.")
    try:
        state.stationkit_controller.initialize_all()
        try:
            init_gui_vars(state)

            if state.root.winfo_exists():
                if state.start_btn:
                    state.start_btn.config(relief=tk.RAISED)
                if state.di1_btn:
                    state.di1_btn.config(relief=tk.RAISED)
                if state.estop_btn:
                    state.estop_btn.config(fg="black", bg="#ffcccc")
                state.estop_var.set(0)
                if state.exclusive_var:
                    state.exclusive_var.set(1)
                state.status_label.config(text="Initialized.")
                add_log("Manual initialization completed.")

            reset_ui_state(state)
        except tk.TclError:
            pass
    except DeviceCommunicationError as err:
        handle_device_comm_error("on_init_btn", err)
    except DeviceTimeoutError as err:
        print(f"Initialization Timeout: {err}")
        if not state.is_closing:
            messagebox.showerror("Initialization Error", str(err))


def on_close(state, add_log):
    print("Application closing...")
    add_log("Application closing...")
    state.is_closing = True
    set_operation_state(state, OperationState.STOPPED, add_log)

    try:
        state.stationkit_controller.disconnect_now()
    except Exception as err:
        print(f"Error closing device: {err}")

    try:
        state.root.destroy()
    except Exception as err:
        print(f"Error destroying window: {err}")
