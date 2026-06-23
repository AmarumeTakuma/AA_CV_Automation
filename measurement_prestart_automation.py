from __future__ import annotations

import datetime
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pyautogui
import pyperclip
import keyboard 
import traceback

from measurement_automation_models import AutomationStep, PrestartAutomationPlan
from runtime_state import OperationState


pyautogui.FAILSAFE = True


@dataclass
class PrestartAutomationResult:
    success: bool
    plan_name: str
    executed_steps: list[str]
    skipped_steps: list[str]
    failed_step: str | None = None


def _get_prestart_settings(state) -> dict[str, Any]:
    settings = getattr(state.config, "measurement_prestart", {})
    return settings if isinstance(settings, dict) else {}


def build_prestart_plan(state, session=None) -> PrestartAutomationPlan:
    settings = _get_prestart_settings(state)

    is_change_settings = getattr(state, "ui_change_settings", False)
    is_set_dio = getattr(state, "ui_set_dio", False)

    if not is_change_settings and not is_set_dio:
        abs_path = ""
        if session:
            raw_path = os.path.join(session.save_dir, session.filename)
            abs_path = os.path.normpath(raw_path)

        return PrestartAutomationPlan(
            name="fast_start_only",
            steps=[
                AutomationStep(name="focus_hoktnet", action="focus_window", payload={"title": "Hoktnet"}, required=True),
                AutomationStep(name="wait_for_window", action="wait", payload={"seconds": 1.0}),
                AutomationStep(name="click_start_button", action="locate_and_click", payload={"image": "start_btn_dummy.png"}, required=True),
                AutomationStep(name="wait_for_save_dialog", action="wait", payload={"seconds": 1.5}),
                AutomationStep(name="input_file_path", action="paste_text", payload={"text": abs_path}, required=True),
                AutomationStep(name="press_enter_to_save", action="press", payload={"keys": ["enter"]}, required=True)
            ],
            notes=["Fast start route triggered by UI checkboxes (Both OFF)."]
        )

    plan_name = settings.get("plan_name", "cv_prestart")
    steps: list[AutomationStep] = []

    for raw_step in settings.get("steps", []):
        if not isinstance(raw_step, dict):
            continue
        step_name = str(raw_step.get("name", raw_step.get("action", "step")))
        action = str(raw_step.get("action", "noop"))
        payload = raw_step.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}
        steps.append(
            AutomationStep(
                name=step_name, action=action, payload=payload,
                required=bool(raw_step.get("required", False)),
                enabled=bool(raw_step.get("enabled", True)),
                description=str(raw_step.get("description", "")),
            )
        )

    if not steps:
        steps = [
            AutomationStep(name="open_quick_start", action="noop", required=False, enabled=False),
            AutomationStep(name="choose_protocol", action="noop", required=False, enabled=False),
            AutomationStep(name="choose_channel", action="noop", required=False, enabled=False),
            AutomationStep(name="configure_dialogs", action="noop", required=False, enabled=False),
            AutomationStep(name="start_measurement_ui", action="noop", required=False, enabled=False),
        ]

    notes = ["Unspecified UI details are intentionally left as configurable no-ops."]
    if session is not None:
        notes.append(f"Target cell: {session.target_cell}")

    return PrestartAutomationPlan(name=plan_name, steps=steps, notes=notes)


def _resolve_point(payload: dict[str, Any]) -> tuple[int, int] | None:
    point = payload.get("point")
    if isinstance(point, (list, tuple)) and len(point) == 2:
        try:
            return int(point[0]), int(point[1])
        except (TypeError, ValueError):
            return None
    return None

def _is_estop_requested(state):
    if hasattr(state, "root") and state.root.winfo_exists():
        state.root.update()
        
    if hasattr(state, "device") and hasattr(state.device, "send_heartbeat"):
        current_time = time.time()
        if not hasattr(state, "last_hb_time") or current_time - state.last_hb_time > 0.5:
            try:
                state.device.send_heartbeat()
                state.last_hb_time = current_time
            except Exception:
                pass

    if getattr(state, "operation_state", None) == OperationState.ESTOP_PENDING:
        return True
    
    if keyboard.is_pressed('esc'):
        state.operation_state = OperationState.ESTOP_PENDING 
        return True
        
    return False

def _trigger_auto_estop(state, add_log, reason):
    """RPAの致命的なエラー検知時に、システム全体の緊急停止をキックする"""
    add_log(f"[ALERT] AUTO E-STOP Triggered by RPA: {reason}")
    print(f"!!! AUTO E-STOP Triggered: {reason} !!!")
    
    state.estop_var.set(1)
    state.operation_state = OperationState.ESTOP_PENDING
    
    def _do_estop():
        try:
            from measurement_workflow import on_estop
            
            def fallback_handler(ctx, err):
                add_log(f"[Comm Error during Auto E-STOP] {ctx}: {err}")
            
            on_estop(state, add_log, fallback_handler)
            
            messagebox.showerror(
                "Auto E-STOP Triggered",
                f"The system has been emergency stopped due to an error detected during the automation process.\n\n"
                f"[Reason]\n{reason}\n\n"
                f"* Please check the terminal log for detailed error traces."
            )
            
        except Exception as e:
            add_log(f"[System] Failed to execute auto estop: {e}")

    if state.root.winfo_exists():
        state.root.after(0, _do_estop)

def _run_action(state, step: AutomationStep):
    payload = step.payload or {}

    if _is_estop_requested(state):
        return False

    if step.action == "noop":
        return True

    if step.action == "hotkey":
        keys = payload.get("keys", [])
        if not keys: return False
        pyautogui.hotkey(*[str(key) for key in keys])
        return True

    if step.action == "press":
        keys = payload.get("keys", [])
        if not keys: return False
        for key in keys:
            if _is_estop_requested(state): return False
            pyautogui.press(str(key))
        return True

    if step.action == "write_text":
        text = str(payload.get("text", ""))
        if not text: return False
        pyautogui.write(text, interval=float(payload.get("interval", 0.01)))
        return True

    if step.action == "paste_text":
        text = str(payload.get("text", ""))
        if not text: return False
        if _is_estop_requested(state): return False
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
        return True

    if step.action == "click":
        point = _resolve_point(payload)
        if point is not None:
            pyautogui.click(point[0], point[1], clicks=int(payload.get("clicks", 1)), button=str(payload.get("button", "left")))
            return True
        return False
    
    if step.action == "locate_and_click":
        image_path = str(payload.get("image", ""))
        timeout = 3.0 
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if _is_estop_requested(state): return False
                
            try:
                x, y = pyautogui.locateCenterOnScreen(image_path, confidence=0.9)
                
                pyautogui.moveTo(x, y)
                
                hover_start = time.time()
                while time.time() - hover_start < 0.3:
                    if _is_estop_requested(state):
                        print("E-STOP interrupt right before click! Discarding operation.")
                        return False
                    time.sleep(0.05)
                
                if _is_estop_requested(state): return False
                pyautogui.click()
                return True
            except pyautogui.ImageNotFoundException:
                start_w = time.time()
                while time.time() - start_w < 0.2:
                    if _is_estop_requested(state): return False
                    time.sleep(0.05)
            except Exception as e:
                print(f"[Error] Failed to click image '{image_path}': {e}\n{traceback.format_exc()}")
                return False
                
        print(f"[Error] Image '{image_path}' not found on screen after {timeout} seconds.")
        return False

    if step.action == "wait":
        seconds = float(payload.get("seconds", 0.5))
        start_w = time.time()
        while time.time() - start_w < seconds:
            if _is_estop_requested(state): return False
            time.sleep(0.05)
        return True

    if step.action == "focus_window":
        title = str(payload.get("title", ""))
        if not title: return False
        try:
            import win32gui
            import win32con

            def _enum_handler(hwnd, results):
                if win32gui.IsWindowVisible(hwnd) and title.lower() in win32gui.GetWindowText(hwnd).lower():
                    results.append(hwnd)

            matches: list[int] = []
            win32gui.EnumWindows(_enum_handler, matches)
            if not matches: return False
            
            hwnd = matches[0]
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.3) 

            foreground_hwnd = win32gui.GetForegroundWindow()
            if foreground_hwnd != hwnd:
                try:
                    pyautogui.press('alt')
                    pyautogui.press('esc')
                    time.sleep(0.1)
                    if _is_estop_requested(state): return False
                    win32gui.SetForegroundWindow(hwnd)
                    win32gui.BringWindowToTop(hwnd)
                except Exception as e:
                    print(f"[Error] SetForegroundWindow Failed for '{title}': {e}\n{traceback.format_exc()}")
            return True
        except Exception as e:
            print(f"[Error] focus_window Failed for '{title}': {e}\n{traceback.format_exc()}")
            return False

    if step.action == "open_path":
        path_value = str(payload.get("path", ""))
        if not path_value: return False
        pyperclip.copy(path_value)
        pyautogui.hotkey("ctrl", "l")
        pyautogui.hotkey("ctrl", "v")
        pyautogui.press("enter")
        return True

    return False


def run_prestart_automation(state, session, add_log) -> PrestartAutomationResult:
    plan = build_prestart_plan(state, session)
    add_log(f"Prestart automation plan: {plan.name}")

    executed_steps: list[str] = []
    skipped_steps: list[str] = []

    for step in plan.steps:
        if _is_estop_requested(state):
            add_log("[System] RPA loop forced to ABORT mid-process due to E-STOP activation.")
            return PrestartAutomationResult(False, plan.name, executed_steps, skipped_steps, failed_step=step.name)

        if not step.enabled:
            skipped_steps.append(step.name)
            add_log(f"Prestart step skipped: {step.name}")
            continue

        try:
            ok = _run_action(state, step)
            if ok:
                executed_steps.append(step.name)
                add_log(f"Prestart step executed: {step.name}")
                continue

            if step.required:
                add_log(f"Prestart step failed: {step.name}")
                _trigger_auto_estop(state, add_log, f"Failed to execute required step '{step.name}' (Target not found or timeout).")
                return PrestartAutomationResult(False, plan.name, executed_steps, skipped_steps, failed_step=step.name)

            skipped_steps.append(step.name)
        except Exception as err:
            err_msg = f"Exception at '{step.name}': {err}"
            add_log(f"Prestart step error: {err_msg}")
            print(f"{err_msg}\n{traceback.format_exc()}")
            
            if step.required:
                _trigger_auto_estop(state, add_log, f"An unexpected error occurred in required step '{step.name}': {err}")
                return PrestartAutomationResult(False, plan.name, executed_steps, skipped_steps, failed_step=step.name)
            skipped_steps.append(step.name)

    return PrestartAutomationResult(True, plan.name, executed_steps, skipped_steps)


# ▼▼▼ 追加：ガス名からセル名を推測する関数（app_ui.pyと同等） ▼▼▼
def _infer_cell_for_gas_local(gas_name, config):
    upper_name = gas_name.upper().replace("-", " ")
    for cell_name in config.cells_and_electrodes.keys():
        if cell_name.upper() in upper_name:
            return cell_name
    tokens = upper_name.split()
    suffix = None
    for token in reversed(tokens):
        if len(token) == 1 and token.isalpha():
            suffix = token
            break
    if suffix:
        for cell_name in config.cells_and_electrodes.keys():
            cell_tokens = cell_name.upper().replace("-", " ").split()
            if cell_tokens and cell_tokens[-1] == suffix:
                return cell_name
    return None
# ▲▲▲ 追加ここまで ▲▲▲


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
                    
            # ガスのチェックボックスを同期（▼ 修正：推測関数を使用）
            if hasattr(state, "gas_chk_vars"):
                for gas_name, var in state.gas_chk_vars.items():
                    related_cell = _infer_cell_for_gas_local(gas_name, state.config)
                    var.set(related_cell == target_cell)
                    
            # ALL(マスター)のチェックボックスを同期
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