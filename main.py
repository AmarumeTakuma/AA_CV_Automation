import tkinter as tk
from tkinter import messagebox
import serial
import time

# Arduinoが接続されているCOMポートとボーレート
SERIAL_PORT = "COM5"
BAUDRATE = 9600

# --- ルールブックの定義 ---

# 各電極、各サーボモータ、HZ-ProとArduinoのピン番号の対応
# 0番ピンと1番ピンは通信に使われるので使用不可、サーボモータはPWM対応のピンへ
ELECTRODE_MAP = {
    'Cell A-WE': 2, 'Cell A-CE': 4, 'Cell A-RE': 7,
    'Cell B-WE': 8, 'Cell B-CE': 10, 'Cell B-RE': 12,
}
# 'half_angle': 45などと追加すれば拡張機能として利用できる。ただしキーの名前に"angle"を含ませること
SERVO_MAP = {
    'Gas Line A': {'pin': 3,  'on_angle': 90, 'off_angle': 0},
    'Gas Line B': {'pin': 5,  'on_angle': 90, 'off_angle': 0},
    'Gas Purge':  {'pin': 6, 'on_angle': 90, 'off_angle': 0},
}
# HZ-Pro
START_PIN = 11 # DI1
E_STOP_PIN = 13 # CELL-OPEN-IN

# 各電極がどのセルに属するかの定義
CELLS_AND_ELECTRODES = {
    'Cell A': ['Cell A-WE', 'Cell A-CE', 'Cell A-RE'],
    'Cell B': ['Cell B-WE', 'Cell B-CE', 'Cell B-RE'],
}
# 同種の電極のピンが同時に接続されないように設定する排他チャンネル
ELEC_EXCLUSIVE_CHANNELS = {
    'WE Channel': ['Cell A-WE', 'Cell B-WE'],
    'CE Channel': ['Cell A-CE', 'Cell B-CE'],
    'RE Channel': ['Cell A-RE', 'Cell B-RE'],
}
# ガスラインの排他チャンネル
GAS_EXCLUSIVE_CHANNELS = {
    'Gas Channel': ['Gas Line A', 'Gas Line B']
}

# 逆引き辞書を自動生成
REVERSE_ELEC_EXCLUSIVE_CHANNELS = {}
for elec_channel_name, elec_names in ELEC_EXCLUSIVE_CHANNELS.items():
    for elec_name in elec_names:
        REVERSE_ELEC_EXCLUSIVE_CHANNELS[elec_name] = elec_channel_name

REVERSE_GAS_EXCLUSIVE_CHANNELS = {}
for gas_channel_name, gasline_names in GAS_EXCLUSIVE_CHANNELS.items():
    for gasline_name in gasline_names:
        REVERSE_GAS_EXCLUSIVE_CHANNELS[gasline_name] = gas_channel_name

# --- グローバル変数 ---

ser = None

elec_check_vars = {}
master_elec_check_vars = {}
gas_check_vars = {}
start_button = None
estop_var = None
estop_widget = None
all_widgets = []

# --- 関数定義 ---

""" ルールブックの整合性をチェックする """
def validate_configuration():
    # 辞書の名前の整合性チェック
    all_elec_names = set(ELECTRODE_MAP.keys())
    # セルと属する電極の整合性チェック
    for cells_name, elec_names_in_cell in CELLS_AND_ELECTRODES.items():
        for elec_name in elec_names_in_cell:
            if elec_name not in all_elec_names:
                return f"Config Error: Electrode '{elec_name}' in '{cells_name}' not found in ELECTRODE_MAP."
    # 電極排他チャンネルの整合性チェック
    for elec_channel_name, elec_names_in_channel in ELEC_EXCLUSIVE_CHANNELS.items():
        for elec_name in elec_names_in_channel:
            if elec_name not in all_elec_names:
                return f"Config Error: Electrode '{elec_name}' in '{elec_channel_name}' not found in ELECTRODE_MAP."

    all_gasline_names = set(SERVO_MAP.keys())
    # サーボモータについて値の設定と角度の妥当性をチェック
    for gasline_name, settings in SERVO_MAP.items():
        if 'pin' not in settings or 'on_angle' not in settings or 'off_angle' not in settings:
            return f"Config Error: Gas line '{gasline_name}' in GAS_SERVO_MAP is missing essential settings."
        # 'angle'が含まれるすべての角度をチェック
        for key, value in settings.items():
            if 'angle' in key:
                if not (isinstance(value, int) and 0 <= value <= 180):
                    return f"Config Error: '{key}' for '{gasline_name}' must be an integer between 0 and 180."
    # ガスライン排他チャンネルの整合性チェック
    for gas_channel_name, gasline_name_in_channel in GAS_EXCLUSIVE_CHANNELS.items():
        for gasline_name in gasline_name_in_channel:
            if gasline_name not in all_gasline_names:
                return f"Config Error: Gas line '{gasline_name}' in '{gas_channel_name}' not found in SERVO_MAP."
            
    # ピンの重複チェック
    pin_usage = {} 
    # 電極のピンをチェック
    for name, pin in ELECTRODE_MAP.items():
        if pin in pin_usage:
            return f"Config Error: Pin {pin} is duplicated. Used by '{pin_usage[pin]}' and '{name}'."
        pin_usage[pin] = name
    # ガスラインのピンをチェック
    for name, settings in SERVO_MAP.items():
        pin = settings['pin']
        if pin in pin_usage:
            return f"Config Error: Pin {pin} is duplicated. Used by '{pin_usage[pin]}' and '{name}'."
        pin_usage[pin] = name
    # HZ-Pro用のピンをチェック
    if START_PIN in pin_usage:
        return f"Config Error: Start Pin {START_PIN} is duplicated. Used by '{pin_usage[START_PIN]}'."
    pin_usage[START_PIN] = "Start Pin"
    if E_STOP_PIN in pin_usage:
        return f"Config Error: E-STOP Pin {E_STOP_PIN} is duplicated. Used by '{pin_usage[E_STOP_PIN]}'."
    pin_usage[E_STOP_PIN] = "E-STOP Pin"

    return None

""" Arduinoにコマンドを送信する """
def send_command(command_to_send):
    if not (ser and ser.is_open):
        status_label.config(text="Error: Not connected.")
        return
    
    try:
        ser.write(command_to_send.encode())
        print(f"Sent: {command_to_send.strip()}")
        return True
    except serial.SerialException as e:
        print(f"\n--- COMMUNICATION ERROR ---\nDetails: {e}\n--------------------\n")
        messagebox.showerror("Communication Error", f"Failed to send command.\nConnection may be lost.\n\nError: {e}")
        status_label.config(text="Disconnected. Please restart the application.")
        disable_all_widgets_on_error()
        return False

""" Arduinoとの通信を試みる """
def connect_to_arduino():
    global ser
    try:
        ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=1)
        time.sleep(2)
        status_label.config(text=f"Connected to {SERIAL_PORT}. Initializing electrodes...")
        if not initialize_all_devices():
            raise serial.SerialException("Failed to initialize devices during connection.")
        status_label.config(text=f"Connected and Ready.")
    except serial.SerialException as e:
        print(f"\n--- CONNECTION ERROR ---\nDetails: {e}\n------------------------\n")
        messagebox.showerror("Connection Error", f"Could not open port {SERIAL_PORT}.\n\nPlease check connection.\n\nError: {e}")
        window.destroy()

""" 管理下の全デバイス、電極、サーボモータを初期状態(OFF)にする """
def initialize_all_devices():
    if not (ser and ser.is_open): return False

    success = True
    # 電極をすべて切断、UI更新
    for elec_pin in ELECTRODE_MAP.values():
        if not send_command(f"DO,{elec_pin},0\n"): success = False # DigitalOutput用コマンドは DO,pin,0/1
        time.sleep(0.05)
    for var in elec_check_vars.values(): var.set(0)
    for var in master_elec_check_vars.values(): var.set(0)
    # サーボモータをすべてOFF角度へ、UI更新
    for settings in SERVO_MAP.values():
        servo_pin = settings['pin']
        off_angle = settings['off_angle']
        if not send_command(f"SV,{servo_pin},{off_angle}\n"): success = False # サーボ用コマンドは SV,pin,angle
        time.sleep(0.1)
    for var in gas_check_vars.values(): var.set(0)
    # HZ-ProのDIをすべてHIGHへ（Active Lowにするので待機時はHIGH）、UI更新
    if not send_command(f"DO,{START_PIN},1\n"): success = False
    time.sleep(0.05)
    if not send_command(f"DO,{E_STOP_PIN},1\n"): success = False
    if estop_var: estop_var.set(0)
    # UIのロック解除、測定開始/エマストボタン状態リセット
    toggle_ui_lock(False)
    if start_button: start_button.config(state=tk.NORMAL, relief=tk.RAISED)
    if estop_widget:
        estop_widget.config(fg="black", font=("Arial", 9, "bold"))

    print("Device initialization attempt finished.")
    if 'status_label' in globals() and status_label.winfo_exists():
        status_label.config(text="Device initialization finished.")
    return success

""" 測定中UIをロックする処理 """
def toggle_ui_lock(is_locked): # True：ロック、False：解除
    # エマストのみ操作可能
    allowed_widgets = [estop_widget]

    for widget in all_widgets:
        if widget in allowed_widgets:
            continue
            
        if is_locked:
            widget.config(state=tk.DISABLED)
        else:
            widget.config(state=tk.NORMAL)

""" 一括操作チェックボックスがクリックされたときの処理 """
def on_master_checkbox_click(cell_name):
    if not (ser and ser.is_open): return

    state = master_elec_check_vars[cell_name].get()
    electrodes_in_cell = CELLS_AND_ELECTRODES[cell_name]
    if state == 0:
        #このセルをすべて切断する
        for elec_name in electrodes_in_cell:
            if elec_check_vars[elec_name].get() == 1:
                elec_check_vars[elec_name].set(0)
                on_check_click(elec_name, update_gui=False)
    else:
        # 他のセルをすべて切断する
        for other_cell_name in CELLS_AND_ELECTRODES:
            if other_cell_name != cell_name:
                for elec_name in CELLS_AND_ELECTRODES[other_cell_name]:
                    if elec_check_vars[elec_name].get() == 1:
                        elec_check_vars[elec_name].set(0)
                        on_check_click(elec_name, update_gui=False)
        # このセルをすべて接続する
        for elec_name in electrodes_in_cell:
            if elec_check_vars[elec_name].get() == 0:
                elec_check_vars[elec_name].set(1)
                on_check_click(elec_name, update_gui=False)
    
    # ログを表示
    action_text = "Connected" if state == 1 else "Disconnected"
    status_label.config(text=f"All electrodes in {cell_name} {action_text}.")
    update_all_master_checkboxes()

""" 電極チェックボックスがクリックされたときの処理 """
def on_check_click(clicked_elec_name, update_gui=True):
    if not (ser and ser.is_open): return

    new_state = elec_check_vars[clicked_elec_name].get()
    pin_number = ELECTRODE_MAP.get(clicked_elec_name)

    # ピン番号が未定義であった場合
    if not pin_number:
        error_msg = (f"Config Error:\nElectrode '{clicked_elec_name}' is not defined in ELECTRODE_MAP.\nPlease check the spelling.")
        print(error_msg)
        messagebox.showerror("Configuration Error", error_msg)
        if clicked_elec_name in elec_check_vars:
             elec_check_vars[clicked_elec_name].set(0)
        return
    
    if new_state == 0:
        # この電極を切断する
        send_command(f"DO,{pin_number},0\n")
    else:
        channel_name = REVERSE_ELEC_EXCLUSIVE_CHANNELS.get(clicked_elec_name)
        # 接続したい電極が排他チャンネルに入っていなかった場合
        if not channel_name:
            error_msg = (f"Config Error:\nElectrode '{clicked_elec_name}' is not assigned to any EXCLUSIVE_CHANNELS.\nPlease add it to the correct channel.")
            print(error_msg)
            messagebox.showerror("Configuration Error", error_msg)
            elec_check_vars[clicked_elec_name].set(0)
            return
        # 他セルの同種の電極を切断する
        for elec_name_in_channel in ELEC_EXCLUSIVE_CHANNELS[channel_name]:
            if elec_name_in_channel != clicked_elec_name and elec_name_in_channel in elec_check_vars and elec_check_vars[elec_name_in_channel].get() == 1:
                elec_check_vars[elec_name_in_channel].set(0)
                pin_to_disconnect = ELECTRODE_MAP[elec_name_in_channel]
                send_command(f"DO,{pin_to_disconnect},0\n")
                time.sleep(0.05)
        # この電極を接続する
        send_command(f"DO,{pin_number},1\n")

    # 一括操作以外の場合ではログを表示
    if update_gui:
        action_text = "Connected" if new_state == 1 else "Disconnected"
        status_label.config(text=f"{action_text} {clicked_elec_name}.")
        update_all_master_checkboxes()

""" 親チェックボックスの状態を矛盾がないように更新する """
def update_all_master_checkboxes():
    for cell_name, electrodes_in_cell in CELLS_AND_ELECTRODES.items():
        are_all_electrodes_connected = all(elec_check_vars[elec_name].get() == 1 for elec_name in electrodes_in_cell)
        master_elec_check_vars[cell_name].set(1 if are_all_electrodes_connected else 0)

""" ガスチェックボックスがクリックされたときの処理 """
def on_gas_check_click(clicked_gasline_name, update_gui=True):
    if not (ser and ser.is_open): return

    new_state = gas_check_vars[clicked_gasline_name].get()
    servo_info = SERVO_MAP.get(clicked_gasline_name)

    # ガスラインの情報がなかった場合
    if not servo_info:
        error_msg = (f"Config Error:\nGas line '{clicked_gasline_name}' is not defined in SERVO_MAP.\nPlease check the spelling.")
        print(error_msg)
        messagebox.showerror("Configuration Error", error_msg)
        if clicked_gasline_name in gas_check_vars:
            gas_check_vars[clicked_gasline_name].set(0)
        return

    if new_state == 0:
        # このガスラインを閉じる
        send_command(f"SV,{servo_info['pin']},{servo_info['off_angle']}\n")
    else:
        channel_name = REVERSE_GAS_EXCLUSIVE_CHANNELS.get(clicked_gasline_name)
        # パージ以外のガスラインで真
        if channel_name:
            # 他ガスラインを閉じる
            for gasline_name_in_channel in GAS_EXCLUSIVE_CHANNELS[channel_name]:
                if gasline_name_in_channel != clicked_gasline_name and gasline_name_in_channel in gas_check_vars and gas_check_vars[gasline_name_in_channel].get() == 1:
                    gas_check_vars[gasline_name_in_channel].set(0)
                    servo_info_to_close = SERVO_MAP[gasline_name_in_channel]
                    send_command(f"SV,{servo_info_to_close['pin']},{servo_info_to_close['off_angle']}\n")
                    time.sleep(0.1)
        # このガスラインを開く
        send_command(f"SV,{servo_info['pin']},{servo_info['on_angle']}\n")

    # ログを表示（現時点では常にTrue）
    if update_gui:
        action_text = "Opened" if new_state == 1 else "Closed"
        status_label.config(text=f"Gas line {clicked_gasline_name} {action_text}.")

""" 測定開始ボタンが押されたときの処理 """
def start_measurement():
    if not (ser and ser.is_open): return
    # Active LowなのでLOWを送ってONにする
    send_command(f"DO,{START_PIN},0\n")
    # UI、測定開始ボタンをロック
    toggle_ui_lock(True)
    start_button.config(state=tk.DISABLED, relief=tk.SUNKEN)
    status_label.config(text="Measurement STARTED. Waiting for manual stop (Press E-STOP).")

""" エマストボタンが押されたときの処理 """
def on_estop_click():
    if not (ser and ser.is_open): return
    
    # ユーザーが押してONにしたときのみ動作
    if estop_var.get() == 1:
        # Active Lowでパルス送信
        send_command(f"DO,{E_STOP_PIN},0\n")
        estop_widget.config(fg="white", font=("Arial", 9, "bold"))
        status_label.config(text="Measurement ABORTED via E-STOP. Device Reset.")
        window.update() # GUIを強制更新して表示を反映
        time.sleep(0.5)
        send_command(f"DO,{E_STOP_PIN},1\n")
        
        # 測定開始されないように
        send_command(f"DO,{START_PIN},1\n") 
        
        # UI、測定開始ボタン、エマストボタンのロック解除
        toggle_ui_lock(False)
        start_button.config(state=tk.NORMAL, relief=tk.RAISED)
        estop_var.set(0)
        
        estop_widget.config(fg="black", font=("Arial", 9, "bold"))
        status_label.config(text="E-STOP Released. Ready for next measurement.")
    else:
        # 万が一OFF操作された場合も安全のためHIGHを送っておく
        send_command(f"DO,{E_STOP_PIN},1\n")

""" プログラム進行中、エラーの際にGUI上の全ウィジェットを無効化する """
def disable_all_widgets_on_error():
    for widget in all_widgets:
        widget.config(state=tk.DISABLED)
    if start_button: start_button.config(state=tk.DISABLED)

""" 正常にプログラムを終了する """
def on_closing():
    if ser and ser.is_open:
        initialize_all_devices()
        ser.close()
        print("Serial port closed.")
    window.destroy()

# --- メインの実行部分 ---

if __name__ == '__main__':
    window = tk.Tk()
    window.title("Electrode Controller")

    # 辞書の整合性チェック
    config_error = validate_configuration()
    if config_error:
        print(f"\n--- CONFIGURATION ERROR ---\n{config_error}\n---------------------------\n")
        messagebox.showerror("Configuration Error", config_error)
        window.destroy()

    else:
        # GUI作成
        main_container = tk.Frame(window)
        main_container.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

        # 左側：電極制御
        elec_frame = tk.LabelFrame(main_container, text="Electrode Control", padx=10, pady=5)
        elec_frame.pack(side=tk.LEFT, padx=5, fill=tk.Y, anchor=tk.N)

        groups_container_frame = tk.Frame(elec_frame)
        groups_container_frame.pack()

        for cell_name, electrodes_in_cell in CELLS_AND_ELECTRODES.items():
            # セルごとのフレーム
            cell_frame = tk.LabelFrame(groups_container_frame, text=cell_name, padx=10, pady=5, font=("Helvetica", 11, "bold"))
            cell_frame.pack(side=tk.LEFT, padx=10, pady=5, fill=tk.Y, anchor=tk.N)
            
            # 親チェックボックス
            var_master = tk.IntVar()
            chk_master = tk.Checkbutton(cell_frame, text="Connect / Disconnect All", variable=var_master, command=lambda g=cell_name: on_master_checkbox_click(g))
            chk_master.pack(anchor=tk.W)
            master_elec_check_vars[cell_name] = var_master
            all_widgets.append(chk_master)

            # 子チェックボックス
            for elec_name in electrodes_in_cell:
                electrode_type = elec_name.split('-')[1]
                var = tk.IntVar(value=0)
                checkbox = tk.Checkbutton(cell_frame, text=electrode_type, variable=var, command=lambda a=elec_name: on_check_click(a))
                checkbox.pack(anchor=tk.W, padx=10)
                elec_check_vars[elec_name] = var
                all_widgets.append(checkbox)

        # 右側：ガス制御、HZ-Pro制御
        right_container = tk.Frame(main_container)
        right_container.pack(side=tk.LEFT, padx=5, fill=tk.Y, anchor=tk.N)

        # ガス
        gas_frame = tk.LabelFrame(right_container, text="Gas Control (Servo)", padx=10, pady=10)
        gas_frame.pack(fill=tk.X, anchor=tk.N, pady=(0, 10))

        for gas_name in SERVO_MAP:
            var = tk.IntVar(value=0)
            checkbox = tk.Checkbutton(gas_frame, text=gas_name, variable=var, command=lambda gn=gas_name: on_gas_check_click(gn))
            checkbox.pack(anchor=tk.W)
            gas_check_vars[gas_name] = var
            all_widgets.append(checkbox)

        # HZ-Pro
        measurement_frame = tk.LabelFrame(right_container, text="HZ-Pro Control (Active Low)", padx=10, pady=10)
        measurement_frame.pack(fill=tk.X, anchor=tk.N, pady=(0, 10))

        # 測定開始ボタン
        start_button = tk.Button(measurement_frame, text="Start Measurement", bg="#ccffcc", 
                                 width=20, height=2, command=start_measurement)
        start_button.pack(pady=5)

        # E-STOP ボタン
        estop_var = tk.IntVar(value=0)
        estop_widget = tk.Checkbutton(measurement_frame, text="E-STOP", bg="#ffcccc", variable=estop_var, 
                             indicatoron=0, selectcolor="red", 
                             width=15, height=2, fg="black", font=("Arial", 9, "bold"),
                             command=on_estop_click)
        estop_widget.pack(pady=2)

        # 初期化ボタン
        bottom_frame = tk.Frame(window)
        bottom_frame.pack(side=tk.BOTTOM, pady=10, fill=tk.X, padx=10)

        initialize_button = tk.Button(bottom_frame, text="Initialize All Devices", command=initialize_all_devices)
        initialize_button.pack()
        all_widgets.append(initialize_button)

        # ログ表示のためのラベル
        status_label = tk.Label(window, text="Connecting...", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        status_label.pack(side=tk.BOTTOM, fill=tk.X)
        
        window.protocol("WM_DELETE_WINDOW", on_closing)
        window.after(100, connect_to_arduino)
        
        window.mainloop()