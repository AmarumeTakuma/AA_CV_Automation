import time
from tkinter import messagebox

from device_controller import DeviceCommunicationError, DeviceTimeoutError
from stationkit_measurement_controller import StationChangeTarget
from runtime_state import OperationState


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
    if not state.device.is_connected or state.is_closing or state.operation_state != OperationState.IDLE:
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
    if not state.device.is_connected or state.is_closing or state.operation_state != OperationState.IDLE:
        return

    try:
        selected = state.elec_chk_vars[name].get()
        channel = state.config.pca_relay_map.get(name)

        if channel is None:
            error_msg = (
                f"Config Error:\nElectrode '{name}' is not defined in pca_relay_map.\n"
                "Please check settings."
            )
            print(error_msg)
            messagebox.showerror("Configuration Error", error_msg)
            state.elec_chk_vars[name].set(0)
            return

        if selected == 1:
            if is_exclusive_interlock_enabled(state):
                exc_channel = state.config.reverse_elec_exclusive.get(name)
                if not exc_channel:
                    error_msg = (
                        f"Config Error:\nElectrode '{name}' is not assigned to any exclusive channel.\n"
                        "Please check settings."
                    )
                    print(error_msg)
                    messagebox.showerror("Configuration Error", error_msg)
                    state.elec_chk_vars[name].set(0)
                    return

                for other in state.config.elec_exclusive_channels.get(exc_channel, []):
                    if other != name and other in state.elec_chk_vars and state.elec_chk_vars[other].get():
                        other_channel = state.config.pca_relay_map.get(other)
                        if other_channel is not None:
                            state.elec_chk_vars[other].set(0)
                            state.stationkit_controller.change(
                                StationChangeTarget(kind="electrode", name=other, selected=False)
                            )
                            time.sleep(0.05)
            state.stationkit_controller.change(
                StationChangeTarget(kind="electrode", name=name, selected=True)
            )
        else:
            state.stationkit_controller.change(
                StationChangeTarget(kind="electrode", name=name, selected=False)
            )

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
    if not state.device.is_connected or state.is_closing or state.operation_state != OperationState.IDLE:
        return

    try:
        selected = state.gas_chk_vars[name].get()
        servo = state.config.pca_servo_map.get(name)

        if not servo:
            error_msg = (
                f"Config Error:\nGas line '{name}' is not defined in pca_servo_map.\n"
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
                            other_servo = state.config.pca_servo_map.get(other)
                            if other_servo:
                                state.stationkit_controller.change(
                                    StationChangeTarget(kind="gas", name=other, selected=False)
                                )
                                time.sleep(0.1)
            state.stationkit_controller.change(
                StationChangeTarget(kind="gas", name=name, selected=True)
            )
        else:
            state.stationkit_controller.change(
                StationChangeTarget(kind="gas", name=name, selected=False)
            )

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
    if not state.device.is_connected or state.is_closing or state.operation_state != OperationState.IDLE:
        return

    try:
        enabled = is_exclusive_interlock_enabled(state)
        state.stationkit_controller.set_interlock(enabled)
        
        action_text = "Enabled" if enabled else "Disabled"
        state.status_label.config(text=f"Exclusive Interlock: {action_text}")
        add_log(f"Exclusive Interlock {action_text}.")
        
        # 排他制御が有効化された場合は初期化
        if enabled:
            on_init_btn()
    except (DeviceCommunicationError, DeviceTimeoutError) as err:
        handle_device_comm_error("on_toggle_exclusive", err)
    except Exception as err:
        print(f"Error in on_toggle_exclusive: {err}")


def on_panel_closing(state):
    """Called when the UI panel is closing to save state if necessary."""
    pass
