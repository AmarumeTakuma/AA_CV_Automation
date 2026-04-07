import time
from tkinter import messagebox

from device_controller import DeviceCommunicationError, DeviceTimeoutError


def is_exclusive_interlock_enabled(state):
    """Return True when exclusive interlock mode is enabled in UI."""
    if state.exclusive_var is None:
        return True
    try:
        return bool(state.exclusive_var.get())
    except Exception:
        return True


def update_master_checkboxes(state):
    if state.is_closing:
        return

    for cell, elecs in state.config.cells_and_electrodes.items():
        all_on = all(state.elec_chk_vars[e].get() for e in elecs)
        state.master_chk_vars[cell].set(1 if all_on else 0)


def on_master_click(state, cell_name, on_elec_click, add_log=None):
    if not state.device.is_connected or state.is_closing:
        return

    selected = state.master_chk_vars[cell_name].get()

    if selected == 0:
        for ename in state.config.cells_and_electrodes[cell_name]:
            if state.elec_chk_vars[ename].get():
                state.elec_chk_vars[ename].set(0)
                on_elec_click(ename, update_gui=False)
    else:
        if is_exclusive_interlock_enabled(state):
            for other_cell in state.config.cells_and_electrodes:
                if other_cell != cell_name:
                    state.master_chk_vars[other_cell].set(0)
                    for ename in state.config.cells_and_electrodes[other_cell]:
                        if state.elec_chk_vars[ename].get():
                            state.elec_chk_vars[ename].set(0)
                            on_elec_click(ename, update_gui=False)

        for ename in state.config.cells_and_electrodes[cell_name]:
            if not state.elec_chk_vars[ename].get():
                state.elec_chk_vars[ename].set(1)
                on_elec_click(ename, update_gui=False)

    action_text = "Connected" if selected == 1 else "Disconnected"
    state.status_label.config(text=f"All electrodes in {cell_name} {action_text}.")
    update_master_checkboxes(state)


def on_elec_click(state, name, handle_device_comm_error, update_gui=True):
    if not state.device.is_connected or state.is_closing:
        return

    try:
        selected = state.elec_chk_vars[name].get()
        pin = state.config.electrode_map.get(name)

        if pin is None:
            error_msg = (
                f"Config Error:\nElectrode '{name}' is not defined in electrode_map.\n"
                "Please check settings."
            )
            print(error_msg)
            messagebox.showerror("Configuration Error", error_msg)
            state.elec_chk_vars[name].set(0)
            return

        if selected == 1:
            if is_exclusive_interlock_enabled(state):
                channel = state.config.reverse_elec_exclusive.get(name)
                if not channel:
                    error_msg = (
                        f"Config Error:\nElectrode '{name}' is not assigned to any exclusive channel.\n"
                        "Please check settings."
                    )
                    print(error_msg)
                    messagebox.showerror("Configuration Error", error_msg)
                    state.elec_chk_vars[name].set(0)
                    return

                for other in state.config.elec_exclusive_channels.get(channel, []):
                    if other != name and other in state.elec_chk_vars and state.elec_chk_vars[other].get():
                        other_pin = state.config.electrode_map.get(other)
                        if other_pin is not None:
                            state.elec_chk_vars[other].set(0)
                            state.device.set_digital(other_pin, 0)
                            time.sleep(0.05)
            state.device.set_digital(pin, 1)
        else:
            state.device.set_digital(pin, 0)

        if update_gui:
            state.status_label.config(text=f"{name}: {'ON' if selected else 'OFF'}")
            update_master_checkboxes(state)
    except DeviceCommunicationError as err:
        handle_device_comm_error("on_elec_click", err)
    except DeviceTimeoutError as err:
        print(f"Device Timeout in on_elec_click: {err}")
        if not state.is_closing:
            messagebox.showerror("Device Error", str(err))
    except Exception as err:
        print(f"Error in on_elec_click: {err}")


def on_gas_click(state, name, handle_device_comm_error, update_gui=True):
    if not state.device.is_connected or state.is_closing:
        return

    try:
        selected = state.gas_chk_vars[name].get()
        servo = state.config.servo_map.get(name)

        if not servo:
            error_msg = (
                f"Config Error:\nGas line '{name}' is not defined in servo_map.\n"
                "Please check settings."
            )
            print(error_msg)
            messagebox.showerror("Configuration Error", error_msg)
            if name in state.gas_chk_vars:
                state.gas_chk_vars[name].set(0)
            return

        if selected == 1:
            if is_exclusive_interlock_enabled(state):
                channel = state.config.reverse_gas_exclusive.get(name)
                if channel:
                    for other in state.config.gas_exclusive_channels.get(channel, []):
                        if other != name and other in state.gas_chk_vars and state.gas_chk_vars[other].get():
                            state.gas_chk_vars[other].set(0)
                            other_servo = state.config.servo_map.get(other)
                            if other_servo:
                                state.device.set_servo(other_servo["pin"], other_servo["off_angle"])
                                time.sleep(0.1)
            state.device.set_servo(servo["pin"], servo["on_angle"])
        else:
            state.device.set_servo(servo["pin"], servo["off_angle"])

        if update_gui and not state.is_closing:
            action_text = "Opened" if selected == 1 else "Closed"
            state.status_label.config(text=f"Gas line {name} {action_text}.")
    except DeviceCommunicationError as err:
        handle_device_comm_error("on_gas_click", err)
    except DeviceTimeoutError as err:
        print(f"Device Timeout in on_gas_click: {err}")
        if not state.is_closing:
            messagebox.showerror("Device Error", str(err))
    except Exception as err:
        print(f"Error in on_gas_click: {err}")


def on_toggle_exclusive(state, add_log, on_init_btn, handle_device_comm_error):
    if state.is_closing or state.exclusive_toggle_in_progress:
        return

    state.exclusive_toggle_in_progress = True
    try:
        enabled = is_exclusive_interlock_enabled(state)

        if not enabled:
            proceed = messagebox.askyesno(
                "Disable Interlock",
                "Exclusive interlock will be disabled.\n"
                "This may allow conflicting outputs to be ON at the same time.\n\n"
                "Do you want to continue?",
            )
            if not proceed:
                if state.exclusive_var is not None:
                    state.exclusive_var.set(1)
                state.status_label.config(text="Exclusive interlock: ON")
                add_log("Exclusive interlock disable canceled.")
                return

        if state.device and state.device.is_connected:
            state.device.set_interlock_enabled(enabled)
        state.status_label.config(text=f"Exclusive interlock: {'ON' if enabled else 'OFF'}")
        add_log(f"Exclusive interlock switched {'ON' if enabled else 'OFF'}.")

        if enabled and state.device and state.device.is_connected:
            add_log("Exclusive interlock enabled. Running initialize.")
            on_init_btn()
    except (DeviceCommunicationError, DeviceTimeoutError) as err:
        handle_device_comm_error("on_toggle_exclusive", err)
    except Exception:
        pass
    finally:
        state.exclusive_toggle_in_progress = False


def on_panel_closing(state):
    """Show warning when closing Individual Controls panel while interlock is OFF."""
    if state.is_closing or state.exclusive_var is None:
        return

    if state.exclusive_var.get() == 0:
        messagebox.showinfo(
            "Individual Controls Closing",
            "Exclusive interlock is currently OFF.\n"
            "Conflicting outputs may be active at the same time.",
        )
