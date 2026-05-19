"""Self-contained Notepad save test using PyAutoGUI.

This script starts Notepad, types a short text, opens Save As,
pastes a generated Desktop path for a .txt file, confirms save,
and verifies the file exists (creates a fallback file if needed).

Run:
    python tests_pyautogui/test_run.py

注意: 実際に画面操作を行います。重要な作業を保存してから実行してください。
"""

import datetime
import os
import subprocess
import time

import pyautogui
import pyperclip


TEXT_TO_SAVE = (
    "自動テストによる保存ファイルです。\n"
    "This file is created by tests_pyautogui/test_run.py\n"
)


def make_desktop_path(prefix: str = "pyautogui_test", ext: str = ".txt") -> str:
    if not ext.startswith("."):
        ext = "." + ext
    now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    desktop = os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), "Desktop")
    return os.path.join(desktop, f"{prefix}_{now}{ext}")


def get_window_by_title_keywords(keywords: list[str]):
    for keyword in keywords:
        try:
            windows = pyautogui.getWindowsWithTitle(keyword)
        except Exception:
            windows = []
        if windows:
            return windows[0]
    return None


def activate_window(window) -> bool:
    try:
        if getattr(window, "isMinimized", False):
            window.restore()
            time.sleep(0.15)
        window.activate()
        time.sleep(0.3)
        return True
    except Exception as e:
        print(f"DEBUG: window.activate() failed: {e}")
        return False


def click_inside_window(window, offset_x: int = 140, offset_y: int = 120):
    x = int(window.left + offset_x)
    y = int(window.top + offset_y)
    print(f"DEBUG: click inside window at ({x}, {y})")
    pyautogui.click(x, y)
    time.sleep(0.2)


def close_window_by_coordinates(window) -> bool:
    # Close button is near the top-right of the title bar
    close_x = int(window.left + window.width - 12)
    close_y = int(window.top + 12)
    print(f"DEBUG: clicking close button at ({close_x}, {close_y})")
    pyautogui.click(close_x, close_y)
    time.sleep(0.6)
    return True


def run_notepad_save_test(prefix: str = "pyautogui_test") -> str:
    print("Notepad を起動して保存テストを実行します...")
    proc = subprocess.Popen(["notepad.exe"])
    time.sleep(0.8)

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.08

    notepad = get_window_by_title_keywords(["メモ帳", "Notepad"])
    if notepad is None:
        print("DEBUG: Notepad window not found by title; using active window if possible")
    else:
        print(f"DEBUG: Notepad window found: title={notepad.title!r}, pos=({notepad.left},{notepad.top}) size=({notepad.width},{notepad.height})")
        activate_window(notepad)
        click_inside_window(notepad)

    # Type the body via clipboard paste to avoid missing first characters.
    pyperclip.copy(TEXT_TO_SAVE)
    time.sleep(0.1)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.2)

    # Open Save As
    pyautogui.keyDown("ctrl")
    pyautogui.press("s")
    pyautogui.keyUp("ctrl")
    time.sleep(0.8)

    save_path = make_desktop_path(prefix=prefix, ext=".txt")
    print(f"DEBUG: save_path={save_path}")
    pyperclip.copy(save_path)
    time.sleep(0.1)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(1.0)

    if os.path.exists(save_path):
        print(f"保存が確認できました: {save_path}")
    else:
        print("警告: GUI保存後にファイルが見つかりませんでした。フォールバックで作成します。")
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(TEXT_TO_SAVE)

    # Close Notepad with coordinate click first, then force close if needed.
    if notepad is not None:
        activate_window(notepad)
        close_window_by_coordinates(notepad)

        time.sleep(0.7)
        if proc.poll() is None:
            print("DEBUG: Notepad still running after close click; trying Alt+F4")
            pyautogui.hotkey("alt", "f4")
            time.sleep(0.6)

        if proc.poll() is None:
            print("DEBUG: Notepad still running; forcing taskkill")
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], check=False)
            time.sleep(0.4)

    return save_path


if __name__ == "__main__":
    print("注意: 実際に画面操作を行います。重要な作業を保存してください。")
    input("続行するには Enter を押してください...")
    try:
        saved = run_notepad_save_test()
        print("処理終了。保存先:", saved)
    except pyautogui.FailSafeException:
        print("FAILSAFE トリガー: マウスを左上に移動して操作を中断しました。")
    except KeyboardInterrupt:
        print("テストが中断されました")


def make_desktop_path(prefix="pyautogui_test", ext=".txt"):
    if not ext.startswith("."):
        ext = "." + ext
    now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    desktop = os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), "Desktop")
    return os.path.join(desktop, f"{prefix}_{now}{ext}")


def run_notepad_save_test(prefix="pyautogui_test"):
    print("Notepad を起動して保存テストを実行します...")
    proc = subprocess.Popen(["notepad.exe"])
    time.sleep(0.8)

    # Notepad ウィンドウを前面化して確実にキー入力を受けるようにする
    def find_window_for_pid(pid):
        found = []

        def enum_cb(h, results):
            if win32gui.IsWindowVisible(h):
                _, win_pid = win32process.GetWindowThreadProcessId(h)
                if win_pid == pid:
                    results.append(h)
            return True

        win32gui.EnumWindows(enum_cb, found)
        return found[0] if found else None

    def activate_window_for_pid(pid, timeout=4.0):
        end = time.time() + timeout
        while time.time() < end:
            hwnd = find_window_for_pid(pid)
            if hwnd:
                # デバッグ: PID に紐づくウィンドウタイトルを表示
                try:
                    print(f"DEBUG: found hwnd={hex(hwnd)} title=\"{win32gui.GetWindowText(hwnd)}\"")
                except Exception:
                    pass
                try:
                    # AttachThreadInput を使ってより強力に前面化を試みる
                    cur_tid = win32api.GetCurrentThreadId()
                    win_tid = win32process.GetWindowThreadProcessId(hwnd)[0]
                    fg_hwnd = win32gui.GetForegroundWindow()
                    fg_tid = None
                    if fg_hwnd:
                        fg_tid = win32process.GetWindowThreadProcessId(fg_hwnd)[0]

                    if fg_tid is not None:
                        try:
                            win32api.AttachThreadInput(cur_tid, win_tid, True)
                            win32api.AttachThreadInput(cur_tid, fg_tid, True)
                        except Exception:
                            pass

                    if win32gui.IsIconic(hwnd):
                        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    win32gui.SetForegroundWindow(hwnd)

                    if fg_tid is not None:
                        try:
                            win32api.AttachThreadInput(cur_tid, win_tid, False)
                            win32api.AttachThreadInput(cur_tid, fg_tid, False)
                        except Exception:
                            pass

                    return True
                except Exception:
                    try:
                        win32gui.BringWindowToTop(hwnd)
                        return True
                    except Exception:
                        pass
            time.sleep(0.15)
        return False

    activated = activate_window_for_pid(proc.pid, timeout=4.0)
    if not activated:
        print("注意: Notepad ウィンドウを前面化できませんでした（PID ベース）。キー送信が失敗する可能性があります。")

    pyautogui.PAUSE = 0.12
    pyautogui.FAILSAFE = True

    # テキスト入力 — typewrite で欠ける問題を避けるため、クリップボードで貼り付ける
    text = "自動テストによる保存ファイルです。\nThis file is created by tests_pyautogui/test_run.py\n"
    pyperclip.copy(text)
    time.sleep(0.05)
    pyautogui.hotkey('ctrl', 'v')
    time.sleep(0.2)

    # 保存ダイアログを開く（Ctrl を確実に送るため keyDown/press/keyUp を使う）
    pyautogui.keyDown('ctrl')
    pyautogui.press('s')
    pyautogui.keyUp('ctrl')
    time.sleep(0.6)

    # 保存先のパスを作成してクリップボードにコピー、貼り付け
    save_path = make_desktop_path(prefix=prefix, ext=".txt")
    pyperclip.copy(save_path)
    time.sleep(0.05)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.2)
    pyautogui.press("enter")

    # 保存完了待ち
    time.sleep(0.8)

    # ファイルが存在するか確認。なければフォールバックで作成
    if os.path.exists(save_path):
        print("保存が確認できました:", save_path)
    else:
        try:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, "w", encoding="utf-8") as f:
                f.write("自動フォールバックファイル\nThis is a fallback file created by the test script.\n")
            print("警告: GUIによる保存が確認できなかったため、フォールバックでファイルを作成しました:", save_path)
        except Exception as e:
            print("エラー: フォールバックファイルの作成に失敗しました:", e)

    # Notepad を閉じる: まずウィンドウの右上（閉じるボタン）を座標でクリックする
    time.sleep(0.2)
    hwnd = find_window_for_pid(proc.pid)
    closed = False
    if hwnd:
        try:
            # ウィンドウ矩形を取得して右上にマウス移動してクリック
            rect = win32gui.GetWindowRect(hwnd)  # (left, top, right, bottom)
            left, top, right, bottom = rect
            # 余裕を持たせて中央より少し内側を狙う（環境で調整してください）
            close_x = right - 10
            close_y = top + 10

            try:
                # 前面化を再度試みる
                activate_window_for_pid(proc.pid, timeout=1.0)
            except Exception:
                pass

            print(f"DEBUG: moving mouse to ({close_x},{close_y}) using pyautogui.moveTo")
            moved = False
            try:
                pyautogui.moveTo(close_x, close_y, duration=0.15)
                pyautogui.click()
                moved = True
            except Exception as e:
                print("DEBUG: pyautogui.moveTo/click failed:", e)

            if not moved:
                # フォールバックでネイティブAPIを使って座標設定とクリック
                try:
                    print("DEBUG: fallback using win32api.SetCursorPos and mouse_event")
                    win32api.SetCursorPos((int(close_x), int(close_y)))
                    # MOUSEEVENTF_LEFTDOWN = 0x0002, MOUSEEVENTF_LEFTUP = 0x0004
                    win32api.mouse_event(0x0002, 0, 0, 0, 0)
                    time.sleep(0.05)
                    win32api.mouse_event(0x0004, 0, 0, 0, 0)
                except Exception as e:
                    print("DEBUG: fallback cursor/click failed:", e)

            # デバッグ: 現在のカーソル位置を表示
            try:
                cur = win32api.GetCursorPos()
                print(f"DEBUG: cursor now at {cur}")
            except Exception:
                pass
            time.sleep(0.5)
            if proc.poll() is not None:
                closed = True
            else:
                # クリックで閉じていない場合は、念のため WM_CLOSE を送る
                try:
                    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                except Exception:
                    pass
                time.sleep(0.5)
                if proc.poll() is not None:
                    closed = True
        except Exception as e:
            print("DEBUG: 座標クリックで閉じる処理で例外が発生しました:", e)

    # 最終手段: まだ生きているなら terminate/taskkill
    if not closed and proc.poll() is None:
        # PID に紐づくウィンドウを列挙してすべて WM_CLOSE を送る
        found_hwnds = []
        def enum_cb2(h, results):
            if win32gui.IsWindowVisible(h):
                try:
                    _, win_pid = win32process.GetWindowThreadProcessId(h)
                    if win_pid == proc.pid:
                        results.append(h)
                except Exception:
                    pass
            return True

        win32gui.EnumWindows(enum_cb2, found_hwnds)
        for h in found_hwnds:
            try:
                print(f"DEBUG: posting WM_CLOSE to hwnd={hex(h)} title=\"{win32gui.GetWindowText(h)}\"")
                win32gui.PostMessage(h, win32con.WM_CLOSE, 0, 0)
            except Exception:
                pass

        # 少し待ってプロセスが終了するか確認
        time.sleep(0.6)
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=1)
            except Exception:
                # 最終手段: taskkill で強制終了
                try:
                    print("DEBUG: proc still running, attempting taskkill /F /T")
                    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], check=False)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass

    return save_path


if __name__ == "__main__":
    print("注意: 実際に画面操作を行います。重要な作業を保存してください。")
    input("続行するには Enter を押してください...")
    try:
        saved = run_notepad_save_test()
        print("処理終了。保存先:", saved)
    except pyautogui.FailSafeException:
        print("FAILSAFE トリガー: マウスを左上に移動して操作を中断しました。")
    except KeyboardInterrupt:
        print("テストが中断されました")
