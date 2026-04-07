from tkinter import messagebox

from device_controller import DeviceCommunicationError, DeviceTimeoutError
from runtime_state import OperationState
from selection_manager import is_exclusive_interlock_enabled
from ui_utils import reset_ui_state


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


def check_incoming_data(state, finish_measurement_handler):
    if state.is_closing:
        return

    try:
        line = state.device.read_line()
        while line:
            print(f"[Arduino] {line}")
            if "MEASUREMENT_END" in line:
                finish_measurement_handler()
            line = state.device.read_line()
    except Exception as err:
        print(f"Serial Read Error: {err}")

    try:
        if state.root.winfo_exists() and not state.is_closing:
            state.root.after(100, lambda: check_incoming_data(state, finish_measurement_handler))
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
        if not state.device.connect():
            state.status_label.config(text="Connection failed.")
            add_log("Connection failed.")
            return
    except DeviceCommunicationError as err:
        print(f"Connection Error: {err}")
        if not state.is_closing:
            messagebox.showerror("Connection Error", str(err))
            state.root.destroy()
        return

    state.status_label.config(text=f"Connected to {state.config.serial_port}. Initializing...")
    add_log(f"Connected to {state.config.serial_port}. Initializing...")
    state.root.update()

    if state.is_closing:
        return

    try:
        if state.device.initialize_devices():
            print("Initialization successful. Connected and Ready.")
            try:
                state.device.set_interlock_enabled(is_exclusive_interlock_enabled(state))
                if state.root.winfo_exists():
                    state.status_label.config(text="Connected and Ready.")
                    add_log("Initialization completed. Connected and Ready.")
                    reset_ui_state(state)
            except Exception:
                pass

            check_incoming_data(state, finish_measurement_handler)
            send_heartbeat_loop(state)
            comm_watchdog_loop(state, handle_device_comm_error)
        else:
            print("Initialization Error: Device initialization failed.")
            add_log("Initialization failed.")
            if not state.is_closing:
                messagebox.showerror("Error", "Initialization failed.")
                state.root.destroy()
    except (DeviceCommunicationError, DeviceTimeoutError) as err:
        print(f"Initialization Error: {err}")
        if not state.is_closing:
            messagebox.showerror("Initialization Error", str(err))
            state.root.destroy()
