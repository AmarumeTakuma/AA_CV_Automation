from tkinter import messagebox

from device_controller import DeviceCommunicationError, DeviceTimeoutError
from runtime_state import OperationState
# ▼ 追加：エマスト機能（on_estop）を呼び出すためにインポート
from measurement_workflow import on_estop


def send_heartbeat_loop(state):
    if state.is_closing:
        return
    state.device.send_heartbeat()

    try:
        if state.root.winfo_exists() and not state.is_closing:
            state.root.after(state.config.heartbeat_interval, lambda: send_heartbeat_loop(state))
    except Exception:
        pass


def comm_watchdog_loop(state, handle_device_comm_error):
    if state.is_closing:
        return

    try:
        if (
            state.device
            and state.device.is_connected
            and state.operation_state not in (OperationState.RECOVERING, OperationState.FAULT, OperationState.STOPPED)
        ):
            state.device.probe_communication()
    except (DeviceCommunicationError, DeviceTimeoutError) as err:
        handle_device_comm_error("comm_watchdog", err)
    except Exception as err:
        print(f"Error in comm_watchdog_loop: {err}")

    try:
        if state.root.winfo_exists() and not state.is_closing:
            interval_ms = max(1000, int(state.config.watchdog_timeout / 2))
            state.root.after(interval_ms, lambda: comm_watchdog_loop(state, handle_device_comm_error))
    except Exception:
        pass


def check_incoming_data(state, add_log, handle_device_comm_error, finish_measurement_handler):
    if state.is_closing:
        return

    try:
        line = state.device.read_line()
        while line:
            print(f"[Arduino] {line}")
            
            # 1. 測定終了の検知
            if "MEASUREMENT_END" in line:
                finish_measurement_handler()
            
            # ▼▼▼ 変更：物理エマスト または HW異常 どちらのメッセージでもエマストを発動させる ▼▼▼
            elif "HW_ERR,1" in line or "EMERGENCY_STOP" in line:
                print("!!! HARDWARE/PHYSICAL E-STOP DETECTED FROM DEVICE !!!")
                
                # 何が原因で止まったのか（物理ボタンか、HW異常か）をログに残す
                reason = "Physical Button" if "PHYSICAL" in line else "Measurement Device Error"
                add_log(f"[ALERT] Emergency stop signal received from device! (Reason: {reason}) Triggering UI E-STOP.")
                
                # 自動的にエマスト（緊急停止）処理を発動させる
                state.estop_var.set(1)
                on_estop(state, add_log, handle_device_comm_error)
            # ▲▲▲ 変更ここまで ▲▲▲

            line = state.device.read_line()
    except Exception as err:
        print(f"Serial Read Error: {err}")

    try:
        if state.root.winfo_exists() and not state.is_closing:
            state.root.after(100, lambda: check_incoming_data(state, add_log, handle_device_comm_error, finish_measurement_handler))
    except Exception:
        pass


def connect_app(state, add_log, handle_device_comm_error, finish_measurement_handler):
    if state.is_closing:
        return

    port_exists, available_ports = state.device.check_port_available()

    if not port_exists:
        ports_str = ", ".join(available_ports) if available_ports else "None"
        warn_msg = (
            f"Port '{state.config.serial_port}' is NOT detected on this PC.\n\n"
            f"Available ports: [{ports_str}]\n\n"
            "Do you want to attempt connection anyway?\n"
            "(Select 'No' to abort and check your settings.json)"
        )
        attempt_anyway = messagebox.askyesno("Port Not Found", warn_msg)

        if not attempt_anyway:
            state.status_label.config(text="Connection aborted. Please check COM port.")
            add_log("Connection aborted. Please check COM port.")
            return

    try:
        state.stationkit_controller.connect(state.config.serial_port)

        check_incoming_data(state, add_log, handle_device_comm_error, finish_measurement_handler)
        
        send_heartbeat_loop(state)
        comm_watchdog_loop(state, handle_device_comm_error)
    except (DeviceCommunicationError, DeviceTimeoutError) as err:
        print(f"Initialization Error: {err}")
        if not state.is_closing:
            messagebox.showerror("Initialization Error", str(err))
            state.root.destroy()