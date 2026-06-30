from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any
import tkinter as tk
from tkinter import messagebox

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
            from system_actions import on_estop
            
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