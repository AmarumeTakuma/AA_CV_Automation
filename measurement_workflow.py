import datetime
import time
import tkinter as tk
from tkinter import messagebox

from device_controller import DeviceCommunicationError, DeviceTimeoutError
from measurement_file_service import create_measurement_output_file
from measurement_prestart_automation import run_prestart_automation
from measurement_service import MeasurementSession, collect_selected_electrodes, collect_selected_gas_lines
from measurement_prestart_automation import show_start_dialog
from runtime_state import OperationState
from selection_manager import is_exclusive_interlock_enabled
from ui_utils import init_gui_vars, reset_ui_state, toggle_ui_lock, set_operation_state, can_start_measurement, can_estop


def finish_measurement_handler(state, add_log):
    if state.is_closing:
        return

    try:
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
        try:
            state.status_label.config(text="Measurement COMPLETED.")
        except tk.TclError:
            pass


def execute_start_measurement(state, filename, save_dir, target_cell, add_log, handle_device_comm_error):
    if not can_start_measurement(state):
        return

    # Transition to MEASURING state
    set_operation_state(state, OperationState.MEASURING, add_log)

    try:
        state.current_measurement = MeasurementSession(
            filename=filename,
            save_dir=save_dir,
            target_cell=target_cell,
            protocol_name="CV",
            started_at=datetime.datetime.now(),
            selected_electrodes=collect_selected_electrodes(state.elec_chk_vars),
            selected_gas_lines=collect_selected_gas_lines(state.gas_chk_vars),
            exclusive_interlock_enabled=is_exclusive_interlock_enabled(state),
            serial_port=state.config.serial_port,
        )
        state.measurement_history.append(state.current_measurement)

        add_log(f"Measurement start request: {target_cell} (save: {save_dir}/{filename})")

        prestart_result = run_prestart_automation(state, state.current_measurement, add_log)
        state.current_measurement.automation_plan_name = prestart_result.plan_name
        if not prestart_result.success:
            set_operation_state(state, OperationState.IDLE, add_log)
            return

        if state.device.start_measurement():
            print("Measurement STARTED. (UI Locked)")
            output_path = create_measurement_output_file(
                save_dir=save_dir,
                filename=filename,
                target_cell=target_cell,
                selected_electrodes=state.current_measurement.selected_electrodes,
                selected_gas_lines=state.current_measurement.selected_gas_lines,
                exclusive_interlock_enabled=state.current_measurement.exclusive_interlock_enabled,
                serial_port=state.current_measurement.serial_port,
            )
            add_log(f"Measurement file created: {output_path}")
            state.start_btn.config(relief=tk.SUNKEN)
            state.root.update()
            toggle_ui_lock(state, True)
            state.status_label.config(text=f"Measurement STARTED: {target_cell}")
            add_log("Measurement started.")
            state.last_start_time = time.monotonic()
        else:
            set_operation_state(state, OperationState.IDLE, add_log)
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

    try:
        if state.estop_var.get():
            state.estop_chk.config(bg="red", fg="white", relief=tk.SUNKEN)
            state.status_label.config(text="E-STOP ACTIVATED!")
            state.root.update()

            print("!!! EMERGENCY STOP ACTIVATED !!!")
            add_log("E-STOP activated.")

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
        if state.device.initialize_devices():
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
        else:
            if not state.is_closing:
                messagebox.showerror("Error", "Initialization failed.")
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
        if state.device:
            state.device.close()
    except Exception as err:
        print(f"Error closing device: {err}")

    try:
        state.root.destroy()
    except Exception as err:
        print(f"Error destroying window: {err}")
