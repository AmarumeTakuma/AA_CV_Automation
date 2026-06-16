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

    is_change_settings = getattr(state, "ui_change_settings", False)
    is_set_dio = getattr(state, "ui_set_dio", False)

    # チェックボックスが両方OFFなら「最速測定開始ルート」を生成
    if not is_change_settings and not is_set_dio:
        # UIで入力された保存先パスとファイル名を結合して絶対パスを作成
        # session引数には、UIで入力した情報（MeasurementSession）が渡ってきています
        abs_path = ""
        if session:
            raw_path = os.path.join(session.save_dir, session.filename)
            abs_path = os.path.normpath(raw_path)

        return PrestartAutomationPlan(
            name="fast_start_only",
            steps=[
                AutomationStep(
                    name="focus_hoktnet",
                    action="focus_window",
                    payload={"title": "Hoktnet"}, 
                    required=True
                ),
                AutomationStep(
                    name="wait_for_window",
                    action="wait",
                    payload={"seconds": 1.0} # ウィンドウが前に出てくるまで待つ
                ),
                AutomationStep(
                    name="click_start_button",
                    action="locate_and_click",
                    payload={"image": "start_btn_dummy.png"}, 
                    required=True
                ),
                # ▼▼▼ 保存ダイアログの自動操作 ▼▼▼
                AutomationStep(
                    name="wait_for_save_dialog",
                    action="wait",
                    # 保存ダイアログが出現するまで少し長めに待機（PCの速度に合わせて調整可）
                    payload={"seconds": 1.5} 
                ),
                AutomationStep(
                    name="input_file_path",
                    action="paste_text",
                    # クリップボード経由で絶対パスを「ファイル名」欄にペースト
                    payload={"text": abs_path},
                    required=True
                ),
                AutomationStep(
                    name="press_enter_to_save",
                    action="press",
                    # Enterキーを押して保存実行
                    payload={"keys": ["enter"]},
                    required=True
                )
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
    
    if step.action == "locate_and_click":
        image_path = str(payload.get("image", ""))
        # 最大3秒間、画像が見つかるまで探し続ける（リトライ機能）
        timeout = 3.0 
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # 画面内から画像を探して中心座標を取得（confidence=0.9で少しの誤差を許容）
                x, y = pyautogui.locateCenterOnScreen(image_path, confidence=0.9)
                
                # 一瞬でワープするのではなく、0.5秒かけて「スッ」とマウスを移動させる
                pyautogui.moveTo(x, y, duration=0.5)
                pyautogui.click()
                return True
            except pyautogui.ImageNotFoundException:
                # 見つからなければ0.2秒待ってからもう一度探す
                time.sleep(0.2)
            except Exception as e:
                print(f"[Error] Failed to click image: {e}")
                return False
                
        print(f"[Error] Image '{image_path}' not found on screen after {timeout} seconds.")
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
                # IsWindowVisible を条件に入れ、透明なゴーストウィンドウを完全に除外する
                if win32gui.IsWindowVisible(hwnd) and title.lower() in win32gui.GetWindowText(hwnd).lower():
                    results.append(hwnd)

            matches: list[int] = []
            win32gui.EnumWindows(_enum_handler, matches)
            if not matches:
                print(f"[Error] Window containing '{title}' not found.")
                return False
            
            hwnd = matches[0] # 発見した最初の「目に見える」ウィンドウ

            # 最小化（アイコン化）されている場合は、元のサイズに戻して一瞬待つ
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.3) 

            # 現在最前面にあるウィンドウと違う場合のみ処理
            foreground_hwnd = win32gui.GetForegroundWindow()
            if foreground_hwnd != hwnd:
                try:
                    # Windowsのフォーカス奪取制限を確実に解除するためのAlt空打ち+待機
                    pyautogui.press('alt')
                    # Altキーによるメニューのハイライト状態を解除するために、Escキーを空打ちする
                    pyautogui.press('esc')
                    time.sleep(0.1)
                    
                    win32gui.SetForegroundWindow(hwnd)
                    win32gui.BringWindowToTop(hwnd)
                except Exception as e:
                    print(f"[Error] SetForegroundWindow Failed: {e}")
            
            return True
        except Exception as e:
            print(f"[Error] focus_window Failed: {e}")
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
    dialog.geometry("420x480")
    dialog.transient(state.root)
    dialog.grab_set()

    tk.Label(dialog, text="File name", font=("Arial", 10, "bold")).pack(pady=(15, 0))
    fname_frame = tk.Frame(dialog)
    fname_frame.pack()

    default_name = f"measurement_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    file_name_var = tk.StringVar(value=default_name)
    tk.Entry(fname_frame, textvariable=file_name_var, width=28).pack(side=tk.LEFT)
    tk.Label(fname_frame, text=".act").pack(side=tk.LEFT)

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
    
    tk.Label(dialog, text="Automation Options", font=("Arial", 10, "bold")).pack(pady=(15, 0))

    # 設定変更チェックボックスとラジオボタン
    change_settings_var = tk.BooleanVar(value=False)
    settings_method_var = tk.StringVar(value="file")

    def toggle_settings_options():
        # チェックボックスの状態に応じてラジオボタンを有効化・無効化
        ui_state = tk.NORMAL if change_settings_var.get() else tk.DISABLED
        rb_file.config(state=ui_state)
        rb_direct.config(state=ui_state)

    chk_settings = tk.Checkbutton(dialog, text="Change Settings", variable=change_settings_var, command=toggle_settings_options)
    chk_settings.pack(anchor=tk.W, padx=80)

    settings_opt_frame = tk.Frame(dialog)
    settings_opt_frame.pack(anchor=tk.W, padx=100)

    rb_file = tk.Radiobutton(settings_opt_frame, text="Import from external file", variable=settings_method_var, value="file", state=tk.DISABLED)
    rb_file.pack(anchor=tk.W)
    rb_direct = tk.Radiobutton(settings_opt_frame, text="Configure directly in software", variable=settings_method_var, value="direct", state=tk.DISABLED)
    rb_direct.pack(anchor=tk.W)

    # DIO設定チェックボックス
    dio_var = tk.BooleanVar(value=False)
    chk_dio = tk.Checkbutton(dialog, text="Configure DIO", variable=dio_var)
    chk_dio.pack(anchor=tk.W, padx=80, pady=(5, 0))

    btn_frame = tk.Frame(dialog)
    btn_frame.pack(pady=20)

    def on_confirm():
        filename_base = file_name_var.get().strip()
        save_dir = save_dir_var.get().strip()
        target_cell = cell_var.get().strip()

        # UIで選択された自動化オプションの値を取得
        is_change_settings = change_settings_var.get()
        setting_method = settings_method_var.get()
        is_set_dio = dio_var.get()

        # 必須項目の入力チェック
        if not filename_base:
            messagebox.showwarning("Input Error", "File name is required.")
            return
        if not save_dir:
            messagebox.showwarning("Input Error", "Save directory is required.")
            return
        if not target_cell:
            messagebox.showwarning("Input Error", "Target cell is required.")
            return

        # システムの裏側（state）にチェックボックスの状態を保存
        state.ui_change_settings = is_change_settings
        state.ui_set_dio = is_set_dio
        
        # 実行ログに状態を残す（動作確認用）
        add_log(f"UI Options -> ChangeSettings: {is_change_settings}({setting_method}), SetDIO: {is_set_dio}")

        dialog.destroy()
        
        # 実際に測定開始の裏側処理を呼ぶ関数
        def do_execute():
            execute_start_measurement(
                state=state,
                filename=f"{filename_base}.act",
                save_dir=save_dir,
                target_cell=target_cell,
                add_log=add_log,
                handle_device_comm_error=handle_device_comm_error,
            )

        # カウントダウンを処理する関数（アプリをフリーズさせない仕組み）
        def count_down(n):
            if n > 0:
                try:
                    state.status_label.config(text=f"Starting automation in {n}s... (Please release the mouse)")
                except tk.TclError:
                    pass
                # 1秒後（1000ミリ秒後）に、数字を1減らしてもう一度自分を呼ぶ
                state.root.after(1000, lambda: count_down(n - 1))
            else:
                try:
                    state.status_label.config(text="Automation started.")
                except tk.TclError:
                    pass
                do_execute()

        # カウントダウンを「3秒」からスタート
        count_down(3)

    tk.Button(btn_frame, text="Start", command=on_confirm, bg="#ccffcc", width=14).pack(side=tk.LEFT, padx=8)
    tk.Button(btn_frame, text="Cancel", command=dialog.destroy, width=10).pack(side=tk.LEFT, padx=8)