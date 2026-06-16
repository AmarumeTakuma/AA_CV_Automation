import sys
import tkinter as tk
from tkinter import messagebox

from app_ui import MainUI
from config_manager import ConfigManager
from device_controller import ArduinoDevice
from device_lifecycle import connect_app as connect_app_impl
from error_handler import handle_device_comm_error as handle_device_comm_error_impl
from measurement_workflow import finish_measurement_handler as finish_measurement_handler_impl
from measurement_workflow import on_close as on_close_impl
from measurement_workflow import on_estop as on_estop_impl
from measurement_workflow import on_init_btn as on_init_btn_impl
from measurement_workflow import on_start as on_start_impl
from stationkit_measurement_controller import MeasurementStationController
from runtime_state import RuntimeState
from selection_manager import on_elec_click as on_elec_click_impl
from selection_manager import on_gas_click as on_gas_click_impl
from selection_manager import on_master_click as on_master_click_impl
from selection_manager import on_panel_closing as on_panel_closing_impl
from selection_manager import on_toggle_exclusive as on_toggle_exclusive_impl
from ui_utils import add_log as add_log_impl


state = RuntimeState()


def add_log(message):
    add_log_impl(state, message)


def handle_device_comm_error(context, err):
    handle_device_comm_error_impl(state, context, err, add_log)


def finish_measurement_handler():
    finish_measurement_handler_impl(state, add_log)


def connect_app():
    connect_app_impl(state, add_log, handle_device_comm_error, finish_measurement_handler)


def on_master_click(cell_name):
    on_master_click_impl(state, cell_name, on_elec_click)


def on_elec_click(name, update_gui=True):
    on_elec_click_impl(state, name, handle_device_comm_error, update_gui=update_gui)


def on_gas_click(name, update_gui=True):
    on_gas_click_impl(state, name, handle_device_comm_error, update_gui=update_gui)


def on_toggle_exclusive():
    on_toggle_exclusive_impl(state, add_log, on_init_btn, handle_device_comm_error)


def on_panel_closing():
    on_panel_closing_impl(state)


def on_start():
    on_start_impl(state, add_log, handle_device_comm_error)


def on_estop():
    on_estop_impl(state, add_log, handle_device_comm_error)


def on_init_btn():
    on_init_btn_impl(state, add_log, handle_device_comm_error)


def on_close():
    on_close_impl(state, add_log)


if __name__ == "__main__":
    root = tk.Tk()
    root.title("Electrode Controller")
    root.geometry("900x750")
    state.root = root

    try:
        config = ConfigManager("settings.json")
        err = config.validate()
        if err:
            print(f"[Config Error] {err}")
            messagebox.showerror("Config Error", err)
            sys.exit(1)
        print("Configuration loaded and validated.")
        state.config = config
        state.device = ArduinoDevice(config)
    except Exception as err:
        print(f"[Fatal Error] {err}")
        messagebox.showerror("Initialization Error", str(err))
        sys.exit(1)

    state.stationkit_controller = MeasurementStationController(state, add_log, handle_device_comm_error)

    ui = MainUI(
        root,
        state.config,
        {
            "on_master_click": on_master_click,
            "on_elec_click": on_elec_click,
            "on_gas_click": on_gas_click,
            "on_toggle_exclusive": on_toggle_exclusive,
            "on_panel_closing": on_panel_closing,
            "on_start": on_start,
            "on_estop": on_estop,
            "on_init_btn": on_init_btn,
            "on_close": on_close,
        },
    )
    ui.build()

    state.elec_chk_vars = ui.elec_chk_vars
    state.master_chk_vars = ui.master_chk_vars
    state.gas_chk_vars = ui.gas_chk_vars
    state.all_widgets = ui.lockable_widgets
    state.start_btn = ui.start_btn
    state.di1_btn = ui.start_btn
    state.estop_var = ui.estop_var
    state.estop_chk = ui.estop_chk
    state.estop_btn = ui.estop_chk
    state.exclusive_var = ui.exclusive_var
    state.btn_exit = ui.btn_exit
    state.log_combo = ui.log_combo
    state.status_label = ui.status_label

    add_log("Application started. Ready.")

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.bind("<Escape>", lambda _e: (state.estop_var.set(1), on_estop()))
    root.after(100, connect_app)

    root.mainloop()
