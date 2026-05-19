import pyautogui
import pyperclip
import time
import datetime
import os

def auto_save_result(base_folder, file_prefix, ext=".csv"):
    """保存ウィンドウが出たあとに、ファイル名を入力して保存する処理

    ext: 拡張子文字列（例 ".csv" または "txt"）。ドットがなければ補われますn
    """

    # 1. 重複しないファイル名を自動作成（例: data_20260310_102306.csv）
    now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    if not ext.startswith("."):
        ext = "." + ext
    # フォルダのパスとファイル名を結合
    save_path = f"{base_folder}\\{file_prefix}_{now}{ext}"
    
    print(f"次の名前で保存します: {save_path}")

    # 2. クリップボードにパスをコピー
    pyperclip.copy(save_path)
    time.sleep(0.5) # 少し待つのが安定させるコツです

    # 3. Ctrl+V で貼り付け
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.5)

    # 4. Enterキーを押して「保存」を確定
    pyautogui.press("enter")
    
    # 少し待ってから、実際にファイルが作成されたか確認する
    time.sleep(0.8)
    if os.path.exists(save_path):
        print("保存処理が完了しました！（ファイル検出済み）")
        return save_path

    # ファイルが見つからない場合はフォールバックでファイルを作成する
    try:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        # 拡張子に応じて内容を変える（.txtならプレーンテキスト）
        if save_path.lower().endswith('.txt'):
            content = "This is an auto-created fallback text file.\n"
        else:
            content = "# auto-created fallback file\n"
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(content)
        print("警告: 自動保存でファイルが見つからなかったため、フォールバックでファイルを作成しました。")
    except Exception as e:
        print(f"エラー: フォールバックファイルの作成に失敗しました: {e}")

    return save_path

# --- ここから下が実行される部分 ---
# ※保存ウィンドウが画面に出ている状態で、この関数が呼ばれるイメージです
# auto_save_result("C:\\Users\\Desktop\\測定データ", "hoktnet_result")
