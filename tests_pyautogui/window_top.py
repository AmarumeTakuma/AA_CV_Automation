import time
import win32gui
import win32con

def activate_my_window(window_title):
    print(f"「{window_title}」を探しています...")

    # ① ウィンドウを探す処理
    def enum_windows_callback(hwnd, windows):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            # 大文字小文字を区別せずにタイトルに名前が含まれているかチェック
            if window_title.lower() in title.lower():
                windows.append(hwnd)
        return True

    windows = []
    win32gui.EnumWindows(enum_windows_callback, windows)

    if not windows:
        print("❌ ウィンドウが見つかりません。Hoktnet clientが起動しているか確認してください。")
        return False

    hwnd = windows[0] # 最初に見つかったウィンドウのID（ハンドル）
    print("✅ ウィンドウが見つかりました！最前面に移動させます。")

    # ② 最小化されていたら元に戻す
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        time.sleep(0.2)

    # ③ 強制的に最前面に持ってくる
    win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        # SetForegroundWindowが弾かれた場合の強力な保険
        win32gui.BringWindowToTop(hwnd)

    print("✨ アクティブ化が完了しました！")
    return True

# --- ここから下が実行される部分 ---
if __name__ == "__main__":
    target_name = "Hoktnet client"
    
    # テスト実行（実行する前に、Hoktnet clientを裏に隠したり最小化したりしてみてください）
    activate_my_window(target_name)
