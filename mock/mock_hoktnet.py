import tkinter as tk
from tkinter import messagebox, filedialog
import os

def on_start_click():
    print("[Success] Start button clicked by automation.")
    
    # 標準の「名前を付けて保存」ダイアログを呼び出す
    # 自動化スクリプトは、このダイアログの「ファイル名」欄にパスをペーストしてEnterを押します
    file_path = filedialog.asksaveasfilename(
        title="Save As",
        defaultextension=".act",
        filetypes=[("ACT file", "*.act"), ("All files", "*.*")]
    )
    
    if file_path:
        print(f"[Success] Path received: {file_path}")
        # RPAが正しくパスを入力してEnterを押せたかの確認用ポップアップ
        messagebox.showinfo("Test Complete", f"Automation successfully entered the path!\n\nSaved at:\n{file_path}")
    else:
        print("[Canceled] Save dialog was canceled.")

# ウィンドウの作成
root = tk.Tk()
root.title("Hoktnet Client (Dummy Test Window)")
root.geometry("500x400")
root.configure(bg="#e0e0e0")

label = tk.Label(
    root, 
    text="This is a dummy Hoktnet window.\nTesting the automated save dialog interaction.", 
    bg="#e0e0e0", 
    font=("Arial", 10)
)
# 説明ラベルの位置
label.place(x=20, y=150)

image_path = "start_btn_dummy_full.png"

if os.path.exists(image_path):
    btn_img = tk.PhotoImage(file=image_path)
    start_btn = tk.Button(
        root, 
        image=btn_img, 
        command=on_start_click, 
        bd=0, 
        highlightthickness=0,
        activebackground="#e0e0e0",
        bg="#e0e0e0"
    )
    # ボタンの位置（左上）
    start_btn.place(x=20, y=20)
else:
    error_label = tk.Label(root, text=f"Error: {image_path} not found.\nPlease place it in the same directory.", fg="red", bg="#e0e0e0")
    error_label.place(x=20, y=20)

root.mainloop()