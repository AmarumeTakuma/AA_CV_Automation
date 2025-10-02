import tkinter as tk
from tkinter import messagebox
import serial, time

# ピンの対応表
# 接続を変更した場合はここを変更
# 0番と1番ピンは通信用に使われるので使用不可
# 'エイリアス': 実際のピン番号
PIN_MAP = {
    'sw1': 10,
    'sw2': 4,
    'sw3': 2,
}

ser = None
checkbox_vars = {}

# Arduinoへの接続を試み、成功したらピンを初期化する
# 環境に合わせてCOMポートとボーレートを変更
def connect_to_arduino(port = "COM5", baudrate = 9600):
    global ser
    try:
        ser = serial.Serial(port, baudrate, timeout=1)
        time.sleep(2)  # Arduinoのリセット待機
        status_label.config(text=f"Connected to {port}. Initializing pins...")
        
        # 物理的なピンをLOWに初期化し、GUIのチェックボックスもOFF(0)に設定
        initialize_pins_and_gui()

        status_label.config(text=f"Connected and Ready.")
        return True
    
    # ポートが異なったり他のプログラムが使用中のときエラー
    except serial.SerialException as e:
        messagebox.showerror("Connection Error", f"Failed to open port {port}:\n{e}")
        return False

# 管理下の全ピンをLOWにし、GUIの状態も同期させる
def initialize_pins_and_gui():
    if ser and ser.is_open:
        for alias, pin_number in PIN_MAP.items():
            command = f"{pin_number},0\n"
            ser.write(command.encode())
            checkbox_vars[alias].set(0) # GUIのチェックボックスをOFFにする
            time.sleep(0.05)
        print("All pins initialized to LOW.")

# チェックボックスがクリックされたときの処理
def on_checkbox_click(alias):
    if not (ser and ser.is_open):
        status_label.config(text="Error: Not connected to Arduino.")
        return

    pin_number = PIN_MAP[alias]
    # checkbox_varsから、クリックされたエイリアスに対応する変数を取得し、その状態(0 or 1)を得る
    value = checkbox_vars[alias].get()
    
    command_to_send = f"{pin_number},{value}\n"
    ser.write(command_to_send.encode())
    
    state_text = "ON" if value == 1 else "OFF"
    status_label.config(text=f"Set {alias} (Pin {pin_number}) to {state_text}")
    print(f"Sent: {command_to_send.strip()}")

# ウィンドウを閉じるときの処理
def on_closing():
    if ser and ser.is_open:
        # 終了時にピンを安全のためLOWに戻す
        initialize_pins_and_gui()
        ser.close()
        print("Serial port closed.")
    window.destroy()

# GUIの組み立て
window = tk.Tk()
window.title("Arduino GUI Controller")
window.geometry("300x200")

title_label = tk.Label(window, text="Check/Uncheck to control pins", font=("Helvetica", 12))
title_label.pack(pady=10)

# PIN_MAPに基づいてチェックボックスを動的に作成
for alias in PIN_MAP:
    # チェックボックスの状態(0 or 1)を保持するためのTkinter専用変数
    var = tk.IntVar(value=0)
    
    checkbox = tk.Checkbutton(window, text=alias, variable=var, font=("Arial", 11),
                              command=lambda a=alias: on_checkbox_click(a))
    checkbox.pack(anchor=tk.W, padx=40)
    
    # 後で状態を取得・設定できるように、エイリアスと変数を辞書に保存
    checkbox_vars[alias] = var

status_label = tk.Label(window, text="Connecting...", bd=1, relief=tk.SUNKEN, anchor=tk.W)
status_label.pack(side=tk.BOTTOM, fill=tk.X)

# プログラムの実行
window.protocol("WM_DELETE_WINDOW", on_closing)
window.after(100, connect_to_arduino) # ウィンドウ表示の100ms後に接続処理を開始
window.mainloop()