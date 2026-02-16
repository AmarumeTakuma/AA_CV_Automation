import tkinter as tk
from tkinter import messagebox
import time
import sys

# 自作モジュール
from config_manager import ConfigManager
from device_controller import ArduinoDevice

# ==========================================
# グローバル変数
# ==========================================

# システム・通信系
config = None
device = None
is_closing = False # アプリ終了中の判定フラグ（Trueのときはエラーなど出さずに終了に専念）

# GUIの状態管理（IntVar を格納する辞書）
elec_chk_vars = {} # 電極のチェックボックス状態 (0 or 1)
master_chk_vars = {} # セル全体の一括チェックボックス状態 (0 or 1)
gas_chk_vars = {} # ガスラインのチェックボックス状態 (0 or 1)

# 特殊なボタン・ウィジェット本体
di1_btn = None # DI1トリガーボタン (元 start_btn)
estop_btn = None # エマストのチェックボタン本体 (見た目や色を変える用)
estop_var = None # エマストのON/OFF状態 (0 or 1)

# 全ウィジェットのリスト（UIロック用）
all_widgets = []

# ==========================================
# ロジック関数 (GUIから呼ばれる処理)
# ==========================================

def connect_app():
    if is_closing: return
    
    # 接続前にポートの存在チェック
    port_exists, available_ports = device.check_port_available()
    
    if not port_exists:
        ports_str = ", ".join(available_ports) if available_ports else "None"
        warn_msg = (f"Port '{config.serial_port}' is NOT detected on this PC.\n\n"
                    f"Available ports: [{ports_str}]\n\n"
                    f"Do you want to attempt connection anyway?\n"
                    f"(Select 'No' to abort and check your settings.json)")
        attempt_anyway = messagebox.askyesno("Port Not Found", warn_msg) # 単なる警告ではなく、ユーザーに選択させる (Yes/No)
        
        # ユーザーがNoを選んだら、接続処理をやめて待機状態にする
        if not attempt_anyway:
            status_label.config(text="Connection aborted. Please check COM port.")
            return

    # 実際の接続処理（ポートが存在した、またはYesが押された場合）
    if device.connect():
        status_label.config(text=f"Connected to {config.serial_port}. Initializing...")
        root.update()
        
        if is_closing: return

        if device.initialize_devices():
            print("Initialization successful. Connected and Ready.")
            status_label.config(text="Connected and Ready.")
            reset_ui_state()
            # 定期タスク開始
            check_incoming_data()
            send_heartbeat_loop()
        else:
            print("Initialization Error: Device initialization failed.")
            if not is_closing:
                messagebox.showerror("Error", "Initialization failed.")
                root.destroy()
    # 接続に失敗した場合のエラー
    else:
        print(f"Connection Error: Could not connect to {config.serial_port}.")
        if not is_closing:
            messagebox.showerror("Connection Error", f"Could not open {config.serial_port}.\nDevice may be in use or disconnected.")
            root.destroy()

def send_heartbeat_loop():
    if is_closing: return
    device.send_heartbeat()
    root.after(config.heartbeat_interval, send_heartbeat_loop)

def check_incoming_data():
    if is_closing: return
    
    line = device.read_line()
    while line:
        print(f"[Arduino] {line}")
        if "MEASUREMENT_END" in line:
            finish_measurement_handler()
        line = device.read_line()
    
    root.after(100, check_incoming_data)

def finish_measurement_handler():
    device.stop_measurement()
    reset_ui_state()
    status_label.config(text="Measurement COMPLETED.")

def reset_ui_state():
    toggle_ui_lock(False)
    if start_btn: start_btn.config(state=tk.NORMAL, relief=tk.RAISED)

def toggle_ui_lock(is_locked):
    allowed = [estop_chk]
    for widget in all_widgets:
        if widget in allowed: continue
        widget.config(state=tk.DISABLED if is_locked else tk.NORMAL)

# ==========================================
# ボタン操作イベント
# ==========================================

def on_master_click(cell_name):
    if not device.is_connected: return
    
    state = master_chk_vars[cell_name].get()
    
    if state == 0:
        # このセルを全切断
        for ename in config.cells_and_electrodes[cell_name]:
            if elec_chk_vars[ename].get():
                elec_chk_vars[ename].set(0)
                on_elec_click(ename, update_gui=False)
    else:
        # 他セル切断
        for other_cell in config.cells_and_electrodes:
            if other_cell != cell_name:
                master_chk_vars[other_cell].set(0)
                for ename in config.cells_and_electrodes[other_cell]:
                    if elec_chk_vars[ename].get():
                        elec_chk_vars[ename].set(0)
                        on_elec_click(ename, update_gui=False)
        # このセルを全接続
        for ename in config.cells_and_electrodes[cell_name]:
            if not elec_chk_vars[ename].get():
                elec_chk_vars[ename].set(1)
                on_elec_click(ename, update_gui=False)
    
    update_master_checkboxes()

def on_elec_click(name, update_gui=True):
    if not device.is_connected: return
    
    state = elec_chk_vars[name].get()
    pin = config.electrode_map[name]
    
    if state == 1:
        # 排他制御
        ch = config.reverse_elec_exclusive.get(name)
        if ch:
            for other in config.elec_exclusive_channels[ch]:
                if other != name and elec_chk_vars[other].get():
                    elec_chk_vars[other].set(0)
                    device.set_digital(config.electrode_map[other], 0)
        device.set_digital(pin, 1)
    else:
        device.set_digital(pin, 0)

    if update_gui:
        status_label.config(text=f"{name}: {'ON' if state else 'OFF'}")
        update_master_checkboxes()

def update_master_checkboxes():
    for cell, elecs in config.cells_and_electrodes.items():
        all_on = all(elec_chk_vars[e].get() for e in elecs)
        master_chk_vars[cell].set(1 if all_on else 0)

def on_gas_click(name):
    if not device.is_connected: return
    
    state = gas_chk_vars[name].get()
    s = config.servo_map[name]
    
    if state == 1:
        # 排他制御
        ch = config.reverse_gas_exclusive.get(name)
        if ch:
            for other in config.gas_exclusive_channels[ch]:
                if other != name and gas_chk_vars[other].get():
                    gas_chk_vars[other].set(0)
                    other_s = config.servo_map[other]
                    device.set_servo(other_s['pin'], other_s['off_angle'])
                    time.sleep(0.1)
        device.set_servo(s['pin'], s['on_angle'])
    else:
        device.set_servo(s['pin'], s['off_angle'])
    
    status_label.config(text=f"Gas {name}: {'OPEN' if state else 'CLOSED'}")

def on_start():
    if not device.is_connected: return
    if config.start_pin < 0:
        messagebox.showinfo("Info", "Start Pin Disabled")
        return

    if device.start_measurement():
        print("Measurement STARTED. (UI Locked)")
        start_btn.config(state=tk.DISABLED, relief=tk.SUNKEN)
        toggle_ui_lock(True)
        status_label.config(text="Measurement STARTED.")

def on_estop():
    if not device.is_connected: return
    if config.estop_pin < 0:
        estop_var.set(0)
        reset_ui_state()
        return

    if estop_var.get():
        print("!!! EMERGENCY STOP ACTIVATED !!!")
        device.trigger_estop() # 緊急停止パルス送信 & 測定停止
        estop_chk.config(fg="white", bg="red")
        status_label.config(text="E-STOP ACTIVATED!")
        
        # GUIリセット
        root.update()
        reset_ui_state()
        estop_var.set(0)
        
        # 全体リセット(変数を戻す)
        init_gui_vars()
        estop_chk.config(fg="black", bg="#ffcccc")
        print("E-Stop Released. System Reset.")
        status_label.config(text="E-STOP Released.")
    else:
        # 万が一OFF操作されたらHighに戻す
        device.set_digital(config.estop_pin, 1)

def on_init_btn():
    print("Manual initialization requested.")
    if device.initialize_devices():
        init_gui_vars()
        reset_ui_state()
        status_label.config(text="Initialized.")

def init_gui_vars():
    for v in elec_chk_vars.values(): v.set(0)
    for v in master_chk_vars.values(): v.set(0)
    for v in gas_chk_vars.values(): v.set(0)

def on_close():
    global is_closing
    print("Application closing...")
    is_closing = True
    device.close()
    root.destroy()

# ==========================================
# メイン実行 (GUI構築と初期化)
# ==========================================

if __name__ == '__main__':
    # Tkinterの土台を先に作る（エラーのポップアップを安全に出すため）
    root = tk.Tk()
    root.title("Electrode Controller")

    # 設定の読み込みとデバイスの準備
    try:
        config = ConfigManager("settings.json") # 設定読み込み
        err = config.validate()
        if err:
            print(f"[Config Error] {err}")
            messagebox.showerror("Config Error", err)
            sys.exit(1)
        print("Configuration loaded and validated.")
        device = ArduinoDevice(config) # デバイス管理クラスの作成
    except Exception as e:
        print(f"[Fatal Error] {e}")
        messagebox.showerror("Initialization Error", str(e))
        sys.exit(1)

    main_frame = tk.Frame(root)
    main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    # 左カラム：電極
    left_col = tk.LabelFrame(main_frame, text="Electrodes", padx=5, pady=5)
    left_col.pack(side=tk.LEFT, fill=tk.Y, anchor=tk.N)

    for cell, elecs in config.cells_and_electrodes.items():
        cf = tk.LabelFrame(left_col, text=cell, font=("bold", 10))
        cf.pack(fill=tk.X, pady=5)
        
        mv = tk.IntVar()
        tk.Checkbutton(cf, text="All", variable=mv, 
                       command=lambda c=cell: on_master_click(c)).pack(anchor=tk.W)
        master_chk_vars[cell] = mv
        all_widgets.append(mv) # ロック対象ではないがリストに入れておく

        for ename in elecs:
            ev = tk.IntVar()
            etype = ename.split('-')[1]
            cb = tk.Checkbutton(cf, text=etype, variable=ev, padx=10,
                           command=lambda n=ename: on_elec_click(n))
            cb.pack(anchor=tk.W)
            elec_chk_vars[ename] = ev
            all_widgets.append(cb)

    # 右カラム
    right_col = tk.Frame(main_frame)
    right_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)

    # ガス
    gf = tk.LabelFrame(right_col, text="Gas Control", padx=5, pady=5)
    gf.pack(fill=tk.X, pady=5)
    for gname, s in config.servo_map.items():
        if s.get('pin', -1) < 0: continue
        gv = tk.IntVar()
        cb = tk.Checkbutton(gf, text=gname, variable=gv,
                       command=lambda n=gname: on_gas_click(n))
        cb.pack(anchor=tk.W)
        gas_chk_vars[gname] = gv
        all_widgets.append(cb)

    # 測定制御
    cf = tk.LabelFrame(right_col, text="Measurement", padx=5, pady=5)
    cf.pack(fill=tk.X, pady=5)
    
    start_btn = tk.Button(cf, text="START", bg="#ccffcc", height=2, command=on_start)
    start_btn.pack(fill=tk.X, pady=5)
    
    estop_var = tk.IntVar()
    estop_chk = tk.Checkbutton(cf, text="E-STOP [Esc]", bg="#ffcccc", variable=estop_var,
                               indicatoron=0, selectcolor="red", height=2, 
                               font=("Arial", 9, "bold"), command=on_estop)
    estop_chk.pack(fill=tk.X, pady=5)

    # 下部
    bf = tk.Frame(root)
    bf.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=5)
    
    btn_init = tk.Button(bf, text="Initialize All", width=15, command=on_init_btn)
    btn_init.pack(side=tk.LEFT)
    all_widgets.append(btn_init)
    
    btn_exit = tk.Button(bf, text="Exit", width=15, command=on_close)
    btn_exit.pack(side=tk.RIGHT)
    all_widgets.append(btn_exit)

    status_label = tk.Label(root, text="Ready", bd=1, relief=tk.SUNKEN, anchor=tk.W)
    status_label.pack(side=tk.BOTTOM, fill=tk.X)

    # イベントバインド
    root.protocol("WM_DELETE_WINDOW", on_close)
    root.bind('<Escape>', lambda e: (estop_var.set(1), on_estop()))
    root.after(100, connect_app)

    root.mainloop()