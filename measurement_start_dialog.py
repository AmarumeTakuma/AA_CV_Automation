import datetime
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from runtime_state import OperationState
from measurement_prestart_automation import _is_estop_requested

def show_start_dialog(state, add_log, handle_device_comm_error, execute_start_measurement):
    if state.is_closing:
        return

    dialog = tk.Toplevel(state.root)
    dialog.title("Measurement Setup")
    dialog.geometry("550x550")
    dialog.transient(state.root)
    dialog.grab_set()

    state.active_dialog = dialog

    def on_dialog_close():
        state.active_dialog = None
        dialog.destroy()
    dialog.protocol("WM_DELETE_WINDOW", on_dialog_close)

    tk.Label(dialog, text="File name", font=("Arial", 10, "bold")).pack(pady=(15, 0))
    fname_frame = tk.Frame(dialog)
    fname_frame.pack()

    default_name = f"measurement_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    file_name_var = tk.StringVar(value=default_name)
    tk.Entry(fname_frame, textvariable=file_name_var, width=45).pack(side=tk.LEFT)
    tk.Label(fname_frame, text=".act").pack(side=tk.LEFT)

    tk.Label(dialog, text="Save directory", font=("Arial", 10, "bold")).pack(pady=(10, 0))
    dir_frame = tk.Frame(dialog)
    dir_frame.pack()
    
    history_file_path = ".last_save_dir"
    default_dir = os.path.expanduser("~/Desktop") 
    
    if os.path.exists(history_file_path):
        try:
            with open(history_file_path, "r", encoding="utf-8") as f:
                saved_path = f.read().strip()
                if os.path.isdir(saved_path):
                    default_dir = saved_path
        except Exception:
            pass

    save_dir_var = tk.StringVar(value=default_dir)
    tk.Entry(dir_frame, textvariable=save_dir_var, width=45).pack(side=tk.LEFT)

    def browse_dir():
        chosen = filedialog.askdirectory(initialdir=save_dir_var.get())
        if chosen:
            save_dir_var.set(chosen)

    tk.Button(dir_frame, text="Browse...", command=browse_dir).pack(side=tk.LEFT, padx=5)

    tk.Label(dialog, text="Target cell", font=("Arial", 10, "bold")).pack(pady=(10, 0))
    cell_var = tk.StringVar()
    cells = list(state.config.cells_and_electrodes.keys())
    cell_combo = ttk.Combobox(dialog, textvariable=cell_var, values=cells, state="readonly", width=18)
    if cells:
        cell_combo.current(0)
    cell_combo.pack()
    
    tk.Label(dialog, text="Automation Options", font=("Arial", 10, "bold")).pack(pady=(15, 0))

    change_settings_var = tk.BooleanVar(value=False)
    settings_method_var = tk.StringVar(value="file")

    def toggle_settings_options():
        ui_state = tk.NORMAL if change_settings_var.get() else tk.DISABLED
        rb_file.config(state=ui_state)
        rb_direct.config(state=ui_state)

    chk_settings = tk.Checkbutton(dialog, text="Change Settings", variable=change_settings_var, command=toggle_settings_options)
    chk_settings.pack(anchor=tk.W, padx=120)

    settings_opt_frame = tk.Frame(dialog)
    settings_opt_frame.pack(anchor=tk.W, padx=140)

    rb_file = tk.Radiobutton(settings_opt_frame, text="Import from external file", variable=settings_method_var, value="file", state=tk.DISABLED)
    rb_file.pack(anchor=tk.W)
    rb_direct = tk.Radiobutton(settings_opt_frame, text="Configure directly in software", variable=settings_method_var, value="direct", state=tk.DISABLED)
    rb_direct.pack(anchor=tk.W)

    dio_var = tk.BooleanVar(value=False)
    chk_dio = tk.Checkbutton(dialog, text="Configure DIO", variable=dio_var)
    chk_dio.pack(anchor=tk.W, padx=120, pady=(5, 0))

    btn_frame = tk.Frame(dialog)
    btn_frame.pack(pady=20)

    def on_confirm():
        filename_base = file_name_var.get().strip()
        save_dir = save_dir_var.get().strip()
        target_cell = cell_var.get().strip()

        is_change_settings = change_settings_var.get()
        setting_method = settings_method_var.get()
        is_set_dio = dio_var.get()

        if not filename_base:
            messagebox.showwarning("Input Error", "File name is required.")
            return
        if not save_dir:
            messagebox.showwarning("Input Error", "Save directory is required.")
            return
        if not target_cell:
            messagebox.showwarning("Input Error", "Target cell is required.")
            return

        try:
            with open(history_file_path, "w", encoding="utf-8") as f:
                f.write(save_dir)
        except Exception as e:
            add_log(f"[Warning] Could not save directory history: {e}")

        confirm_msg = (
            f"Start measurement for cell '{target_cell}'.\n\n"
            f"This will exclusively turn ON the electrodes and gas for this cell,\n"
            f"and disconnect all other cells and gases automatically.\n\n"
            f"Do you want to proceed?"
        )
        if not messagebox.askyesno("Confirm Measurement", confirm_msg, parent=dialog):
            return

        try:
            # 1. ハードウェアの切り替え (Controllerへ委譲)
            if hasattr(state, "stationkit_controller") and hasattr(state.stationkit_controller, "apply_exclusive_routing"):
                state.stationkit_controller.apply_exclusive_routing(target_cell)
                add_log(f"Applied exclusive routing for target cell '{target_cell}'.")
            else:
                add_log("[Warning] 'apply_exclusive_routing' method not found in controller. UI updated but hardware not switched.")

            # 2. UIのチェックボックス（見た目）を安全に同期
            target_electrodes = state.config.cells_and_electrodes.get(target_cell, [])
            
            # 個別電極のチェックボックスを同期
            if hasattr(state, "elec_chk_vars"):
                for elec_name, var in state.elec_chk_vars.items():
                    var.set(elec_name in target_electrodes)
                    
            # ガスのチェックボックスを同期
            if hasattr(state, "gas_chk_vars"):
                for gas_name, var in state.gas_chk_vars.items():
                    var.set(gas_name == target_cell)
                    
            # ALL(マスター)のチェックボックスを同期 (app_ui.py より master_chk_vars)
            if hasattr(state, "master_chk_vars"):
                for cell_name, var in state.master_chk_vars.items():
                    var.set(cell_name == target_cell)

        except Exception as e:
            add_log(f"[Device Error] Exclusivity switch failed: {e}")
            messagebox.showerror("Device Error", f"Hardware routing failed. Please check the connection.\n\n{e}", parent=dialog)
            return

        state.ui_change_settings = is_change_settings
        state.ui_set_dio = is_set_dio
        
        add_log(f"UI Options -> ChangeSettings: {is_change_settings}({setting_method}), SetDIO: {is_set_dio}")

        on_dialog_close()
        
        def do_execute():
            if _is_estop_requested(state):
                print("Start aborted right before execution due to E-STOP.")
                return

            execute_start_measurement(
                state=state,
                filename=f"{filename_base}.act",
                save_dir=save_dir,
                target_cell=target_cell,
                add_log=add_log,
                handle_device_comm_error=handle_device_comm_error,
            )

        def count_down(n):
            if getattr(state, "operation_state", None) == OperationState.ESTOP_PENDING:
                add_log("Countdown aborted due to E-STOP.")
                try:
                    state.status_label.config(text="Measurement Start ABORTED (E-STOP).")
                except tk.TclError:
                    pass
                return

            if n > 0:
                try:
                    state.status_label.config(text=f"Starting automation in {n}s... (Please release the mouse)")
                except tk.TclError:
                    pass
                state.root.after(1000, lambda: count_down(n - 1))
            else:
                try:
                    state.status_label.config(text="Automation started.")
                except tk.TclError:
                    pass
                do_execute()

        count_down(3)

    tk.Button(btn_frame, text="Start", command=on_confirm, bg="#ccffcc", width=14).pack(side=tk.LEFT, padx=8)
    tk.Button(btn_frame, text="Cancel", command=on_dialog_close, width=10).pack(side=tk.LEFT, padx=8)