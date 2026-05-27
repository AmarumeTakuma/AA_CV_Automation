from __future__ import annotations

import datetime
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pyautogui
import pyperclip

from measurement_automation_models import AutomationStep, PrestartAutomationPlan


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
                name=step_name,
                action=action,
                payload=payload,
                required=bool(raw_step.get("required", False)),
                enabled=bool(raw_step.get("enabled", True)),
                description=str(raw_step.get("description", "")),
            )
        )

    if not steps:
        steps = [
            AutomationStep(
                name="open_quick_start",
                action="noop",
                required=False,
                enabled=False,
                description="Placeholder for opening the quick start / protocol launcher.",
            ),
            AutomationStep(
                name="choose_protocol",
                action="noop",
                required=False,
                enabled=False,
                description="Placeholder for selecting the CV protocol.",
            ),
            AutomationStep(
                name="choose_channel",
                action="noop",
                required=False,
                enabled=False,
                description="Placeholder for selecting HZ-Pro channel 1.",
            ),
            AutomationStep(
                name="configure_dialogs",
                action="noop",
                required=False,
                enabled=False,
                description="Placeholder for file load and DIO dialog automation.",
            ),
            AutomationStep(
                name="start_measurement_ui",
                action="noop",
                required=False,
                enabled=False,
                description="Placeholder for the final Start click in the external measurement app.",
            ),
        ]

    notes = [
        "Unspecified UI details are intentionally left as configurable no-ops.",
        "Add coordinates, hotkeys, or image templates in settings.json under measurement_prestart.steps.",
    ]
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


def _run_action(step: AutomationStep):
    payload = step.payload or {}

    if step.action == "noop":
        return True

    if step.action == "hotkey":
        keys = payload.get("keys", [])
        if not keys:
            return False
        pyautogui.hotkey(*[str(key) for key in keys])
        return True

    if step.action == "press":
        keys = payload.get("keys", [])
        if not keys:
            return False
        for key in keys:
            pyautogui.press(str(key))
        return True

    if step.action == "write_text":
        text = str(payload.get("text", ""))
        if not text:
            return False
        pyautogui.write(text, interval=float(payload.get("interval", 0.01)))
        return True

    if step.action == "paste_text":
        text = str(payload.get("text", ""))
        if not text:
            return False
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
        return True

    if step.action == "click":
        point = _resolve_point(payload)
        if point is not None:
            pyautogui.click(point[0], point[1], clicks=int(payload.get("clicks", 1)), button=str(payload.get("button", "left")))
            return True
        return False

    if step.action == "wait":
        pyautogui.sleep(float(payload.get("seconds", 0.5)))
        return True

    if step.action == "focus_window":
        title = str(payload.get("title", ""))
        if not title:
            return False
        try:
            import win32gui
            import win32con

            def _enum_handler(hwnd, results):
                if title.lower() in win32gui.GetWindowText(hwnd).lower():
                    results.append(hwnd)

            matches: list[int] = []
            win32gui.EnumWindows(_enum_handler, matches)
            if not matches:
                return False
            hwnd = matches[0]
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
            return True
        except Exception:
            return False

    if step.action == "open_path":
        path_value = str(payload.get("path", ""))
        if not path_value:
            return False
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
        if not step.enabled:
            skipped_steps.append(step.name)
            add_log(f"Prestart step skipped: {step.name}")
            continue

        try:
            ok = _run_action(step)
            if ok:
                executed_steps.append(step.name)
                add_log(f"Prestart step executed: {step.name}")
                continue

            if step.required:
                add_log(f"Prestart step failed: {step.name}")
                return PrestartAutomationResult(False, plan.name, executed_steps, skipped_steps, failed_step=step.name)

            skipped_steps.append(step.name)
            add_log(f"Prestart step left configurable: {step.name}")
        except Exception as err:
            add_log(f"Prestart step error: {step.name}: {err}")
            if step.required:
                return PrestartAutomationResult(False, plan.name, executed_steps, skipped_steps, failed_step=step.name)
            skipped_steps.append(step.name)

    return PrestartAutomationResult(True, plan.name, executed_steps, skipped_steps)


def show_start_dialog(state, add_log, handle_device_comm_error, execute_start_measurement):
    if state.is_closing:
        return

    dialog = tk.Toplevel(state.root)
    dialog.title("Measurement Setup")
    dialog.geometry("420x300")
    dialog.transient(state.root)
    dialog.grab_set()

    tk.Label(dialog, text="File name", font=("Arial", 10, "bold")).pack(pady=(15, 0))
    fname_frame = tk.Frame(dialog)
    fname_frame.pack()

    default_name = f"measurement_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    file_name_var = tk.StringVar(value=default_name)
    tk.Entry(fname_frame, textvariable=file_name_var, width=28).pack(side=tk.LEFT)
    tk.Label(fname_frame, text=".csv").pack(side=tk.LEFT)

    tk.Label(dialog, text="Save directory", font=("Arial", 10, "bold")).pack(pady=(10, 0))
    dir_frame = tk.Frame(dialog)
    dir_frame.pack()
    save_dir_var = tk.StringVar(value=os.getcwd())
    tk.Entry(dir_frame, textvariable=save_dir_var, width=28).pack(side=tk.LEFT)

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

    btn_frame = tk.Frame(dialog)
    btn_frame.pack(pady=20)

    def on_confirm():
        filename_base = file_name_var.get().strip()
        save_dir = save_dir_var.get().strip()
        target_cell = cell_var.get().strip()

        if not filename_base:
            messagebox.showwarning("Input Error", "File name is required.")
            return
        if not save_dir:
            messagebox.showwarning("Input Error", "Save directory is required.")
            return
        if not target_cell:
            messagebox.showwarning("Input Error", "Target cell is required.")
            return

        dialog.destroy()
        execute_start_measurement(
            state=state,
            filename=f"{filename_base}.csv",
            save_dir=save_dir,
            target_cell=target_cell,
            add_log=add_log,
            handle_device_comm_error=handle_device_comm_error,
        )

    tk.Button(btn_frame, text="Start", command=on_confirm, bg="#ccffcc", width=14).pack(side=tk.LEFT, padx=8)
    tk.Button(btn_frame, text="Cancel", command=dialog.destroy, width=10).pack(side=tk.LEFT, padx=8)