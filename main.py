import tkinter as tk
from tkinter import messagebox
import serial
import serial.tools.list_ports
import time
import json
import os
import sys

# 定義

# Arduinoが接続されているCOMポートとボーレート
SERIAL_PORT = ""
BAUDRATE = 0

# 各電極、各サーボ、HZ-ProとArduinoのピン番号の対応
START_PIN = 0 # DI1
E_STOP_PIN = 0 # CELL-OPEN-IN
CELL_DEFINITIONS = {}
SERVO_MAP = {}

# 安全のための制約
STANDARD_BAUDRATES = [300, 1200, 2400, 4800, 9600, 14400, 19200, 38400, 57600, 115200] # ボーレートの標準値
REQUIRED_ELECTRODES = {'WE', 'CE', 'RE'} # 電極構成
MAX_PIN_NUMBER = 0 # ピン番号の最大値（誤入力防止）
PROHIBITED_PINS = [] # 使用禁止ピン（通信用 RX/TX）
BUILTIN_LED_PIN = 0 # 警告対象ピン（起動時にLチカするピン）
MIN_ANGLE_DIFF = 0 # サーボのON/OFF角度の最低差（不感帯対策）
WATCHDOG_TIMEOUT = 0
HEARTBEAT_INTERVAL = 0

# 自動生成の辞書
ELECTRODE_MAP = {} # 各電極とピンの対応（例: 'Cell A-WE': 2）
CELLS_AND_ELECTRODES = {} # 各電極がどのセルに属するかの定義（例: 'Cell A': ['Cell A-WE', 'Cell A-CE', 'Cell A-RE']）
ELEC_EXCLUSIVE_CHANNELS = {} # 同種の電極のピンが同時に接続されないように設定する排他チャンネル（例: 'WE Channel': ['Cell A-WE', 'Cell B-WE'],）
GAS_EXCLUSIVE_CHANNELS = {} # ガスラインの排他チャンネル（例: 'Gas Channel': ['Gas Line A', 'Gas Line B']）
# 排他チャンネルの逆引き辞書
REVERSE_ELEC_EXCLUSIVE_CHANNELS = {} # 電極排他チャンネルの逆引き辞書（例: 'Cell A-WE': 'WE Channel')
REVERSE_GAS_EXCLUSIVE_CHANNELS = {} # ガスライン排他チャンネルの逆引き辞書（例: 'Gas Line A': 'Gas Channel')

# --- グローバル変数 ---

ser = None
is_measuring = False # 測定中フラグ
is_closing = False # アプリ終了中フラグ

# GUIの状態管理
elec_check_vars = {}
master_elec_check_vars = {}
gas_check_vars = {}
start_button = None
estop_var = None
estop_widget = None
all_widgets = []

# --- 関数定義 ---

"""settings.json から設定を読み込む"""
def load_settings(filename="settings.json"):
    global SERIAL_PORT, BAUDRATE
    global START_PIN, E_STOP_PIN
    global CELL_DEFINITIONS, SERVO_MAP
    global MAX_PIN_NUMBER, PROHIBITED_PINS, BUILTIN_LED_PIN, MIN_ANGLE_DIFF
    global WATCHDOG_TIMEOUT, HEARTBEAT_INTERVAL

    # 実行ファイル（main.pyまたはexe）と同じ場所にあるJSONを探す
    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable) # .exe
    else:
        application_path = os.path.dirname(os.path.abspath(__file__)) # .py
    
    json_path = os.path.join(application_path, filename)

    # ファイルの存在確認
    if not os.path.exists(json_path):
        messagebox.showerror("Configuration Error", f"Configuration file not found:\n{json_path}")
        sys.exit(1)

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # System Settings
        sys_conf = data.get("system", {})
        SERIAL_PORT = sys_conf.get("port", "") # なかった場合、予測できないのでとりあえず空文字にして後でエラー
        BAUDRATE = sys_conf.get("baudrate", 9600) # なかった場合とりあえず一般的な値へ

        # Pin Assignments
        pins_conf = data.get("pins", {})
        # なかった場合とりあえず0番ピンにして、動作しないように
        START_PIN = pins_conf.get("start", 0)
        E_STOP_PIN = pins_conf.get("estop", 0)

        # Maps
        # JSON構造: "Cell A": {"WE": 2, "CE": 3...}, "Gas Line A": {"pin": 5, "on_angle": 90...}
        # なかった場合、空辞書にして後のループ処理で落ちないように
        CELL_DEFINITIONS = data.get("cells", {})
        SERVO_MAP = data.get("servos", {})

        # Safety Settings
        safe_conf = data.get("safety", {})
        # なかった場合とりあえず一般的な値へ
        MAX_PIN_NUMBER = safe_conf.get("max_pin", 70)
        PROHIBITED_PINS = safe_conf.get("prohibited_pins", [])
        BUILTIN_LED_PIN = safe_conf.get("builtin_led_pin", 13)
        MIN_ANGLE_DIFF = safe_conf.get("min_angle_diff", 5)

        WATCHDOG_TIMEOUT = safe_conf.get("watchdog_timeout_ms", 3000)
        HEARTBEAT_INTERVAL = max(100, int(WATCHDOG_TIMEOUT / 3)) # タイムアウトの 1/3 の間隔で送信（最低100msは確保）
        
        print(f"Loaded configuration file: {json_path}")

    except json.JSONDecodeError as e:
        messagebox.showerror("Configuration Error", f"Invalid JSON format:\n{e}")
        sys.exit(1)
    except Exception as e:
        messagebox.showerror("Configuration Error", f"Unexpected error during configuration loading:\n{e}")
        sys.exit(1)

"""読み込んだ設定をもとに、排他チャンネルや逆引き辞書を生成する関数"""
def generate_maps():
    global ELECTRODE_MAP, CELLS_AND_ELECTRODES
    global ELEC_EXCLUSIVE_CHANNELS, GAS_EXCLUSIVE_CHANNELS
    global REVERSE_ELEC_EXCLUSIVE_CHANNELS, REVERSE_GAS_EXCLUSIVE_CHANNELS

    # マップの初期化（再読み込み対応）
    ELECTRODE_MAP = {}
    CELLS_AND_ELECTRODES = {}
    ELEC_EXCLUSIVE_CHANNELS = {}
    GAS_EXCLUSIVE_CHANNELS = {}
    REVERSE_ELEC_EXCLUSIVE_CHANNELS = {}
    REVERSE_GAS_EXCLUSIVE_CHANNELS = {}

    # 電極関係
    for cell_name, pins in CELL_DEFINITIONS.items():
        elec_list = []
        for elec_type, pin in pins.items():
            # セルに属するように電極名を作成 (例: "Cell A-WE")
            elec_name = f"{cell_name}-{elec_type}"

            ELECTRODE_MAP[elec_name] = pin

            elec_list.append(elec_name) # CELLS_AND_ELECTRODES のためのリスト作成
            
            # 排他チャンネルへの割り振り (例: "WE Channel" にすべてのWEをまとめる)
            channel_name = f"{elec_type} Channel"
            if channel_name not in ELEC_EXCLUSIVE_CHANNELS:
                ELEC_EXCLUSIVE_CHANNELS[channel_name] = []

            ELEC_EXCLUSIVE_CHANNELS[channel_name].append(elec_name)

        CELLS_AND_ELECTRODES[cell_name] = elec_list

    # サーボ関係（排他チャンネル）
    for name, props in SERVO_MAP.items():
        if 'group' in props:
            group_name = props['group']
            if group_name not in GAS_EXCLUSIVE_CHANNELS:
                GAS_EXCLUSIVE_CHANNELS[group_name] = []

            GAS_EXCLUSIVE_CHANNELS[group_name].append(name)

    # 逆引き辞書
    for elec_channel_name, elec_names in ELEC_EXCLUSIVE_CHANNELS.items():
        for elec_name in elec_names:
            REVERSE_ELEC_EXCLUSIVE_CHANNELS[elec_name] = elec_channel_name

    for gas_channel_name, gasline_names in GAS_EXCLUSIVE_CHANNELS.items():
        for gasline_name in gasline_names:
            REVERSE_GAS_EXCLUSIVE_CHANNELS[gasline_name] = gas_channel_name
            
    print("Internal maps generated.")

""" ルールブックの整合性をチェックする """
def validate_configuration():
    # 設定が空ならエラー
    if not CELL_DEFINITIONS and not SERVO_MAP:
        return "Config Error: No Cells and No Gas Lines defined.\nPlease configure CELL_DEFINITIONS or SERVO_MAP."

    # 電極設定のチェック

    for cell_name, pins in CELL_DEFINITIONS.items():
        defined_types = set(pins.keys())
        missing_electrodes = REQUIRED_ELECTRODES - defined_types
        
        # WE（作用極）がない場合はエラー
        if 'WE' in missing_electrodes:
            return f"Config Error: '{cell_name}' is missing 'WE' (Working Electrode).\nEvery cell must have a WE."
            
        # CE（対極）やRE（参照極）がない場合は警告
        if missing_electrodes:
            missing_str = ", ".join(missing_electrodes)
            warn_msg = f"Config Warning: '{cell_name}' is missing electrodes: [{missing_str}].\nStandard CV requires WE, CE, and RE.\n(Ignore this if using 2-electrode setup)"
            messagebox.showwarning("Configuration Warning", warn_msg)

    # サーボモータ設定のチェック

    for gasline_name, settings in SERVO_MAP.items():
        # オンオフ角度が存在することをチェック
        if 'pin' not in settings or 'on_angle' not in settings or 'off_angle' not in settings:
            return f"Config Error: Gas line '{gasline_name}' in GAS_SERVO_MAP is missing essential settings."
        
        # それらがの差が小さすぎないことをチェック
        angle_diff = abs(settings['on_angle'] - settings['off_angle'])
        if angle_diff < MIN_ANGLE_DIFF:
            return f"Config Warning: Gas line '{gasline_name}' angles are too close (Diff: {angle_diff}°).\nMechanical backlash may prevent reliable switching.\nRecommended difference is > {MIN_ANGLE_DIFF}°."
        
        # 'angle'が含まれるすべての角度が適切かチェック
        for key, value in settings.items():
            if 'angle' in key:
                if not (isinstance(value, int) and 0 <= value <= 180):
                    return f"Config Error: '{key}' for '{gasline_name}' must be an integer between 0 and 180."
    
    # ガスラインに、メンバーが1つだけのグループがないかチェック（グループ名のタイプミスを検知）
    for group_name, members in GAS_EXCLUSIVE_CHANNELS.items():
        if len(members) < 2:
            return f"Safety Warning: Gas Group '{group_name}' has only 1 member ({members}).\nExclusive control requires at least 2 members.\nCheck for typos in 'group' name in SERVO_MAP."
            
    # ピン設定のチェック（ピンのタイプミスを検知）

    # 重複チェック
    pin_usage = {} # 使用されているピン一覧（例: 2: 'Cell A-WE'）
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
        return f"Config Error: Trigger Pin {START_PIN} is duplicated. Used by '{pin_usage[START_PIN]}'."
    pin_usage[START_PIN] = "Start Pin"
    if E_STOP_PIN in pin_usage:
        return f"Config Error: E-STOP Pin {E_STOP_PIN} is duplicated. Used by '{pin_usage[E_STOP_PIN]}'."
    pin_usage[E_STOP_PIN] = "E-STOP Pin"

    for pin, user in pin_usage.items():
        # 通信用ピン(0, 1)の使用禁止チェック
        if pin in PROHIBITED_PINS:
            return f"Safety Error: Pin {pin} is reserved for Serial Communication (RX/TX).\nUsed by '{user}'.\nPlease use Pin 2 or higher."

        # 型と範囲のチェック（整数 かつ 0以上70以下）
        if not (isinstance(pin, int) and 0 <= pin <= MAX_PIN_NUMBER):
            return f"Config Error: Pin '{pin}' used by '{user}' is invalid.\nPin must be an integer between 0 and {MAX_PIN_NUMBER}.\n(Check for typos or negative numbers)"
        
    # Pin 13の使用を警告（起動時にLEDが点滅するため、リレーや弁を繋ぐと暴走するリスクがある）
    if BUILTIN_LED_PIN in pin_usage:
        user = pin_usage[BUILTIN_LED_PIN]
        warn_msg = f"Safety Warning: Pin {BUILTIN_LED_PIN} is used by '{user}'.\nPin 13 toggles during Arduino boot (builtin LED).\nThis may cause unexpected actuation on startup.\nRecommend using another pin."
        messagebox.showwarning("Configuration Warning", warn_msg)

    # ボーレートの標準値チェック（警告）
    if BAUDRATE not in STANDARD_BAUDRATES:
        warn_msg = f"Config Warning: BAUDRATE {BAUDRATE} is non-standard.\nStandard values: {STANDARD_BAUDRATES}.\nCheck connection settings if communication fails."
        messagebox.showwarning("Configuration Warning", warn_msg)

    # 指定されたCOMポートが現在PCに認識されているか確認する
    try:
        # PC上の全ポートを取得
        available_ports = [p.device for p in serial.tools.list_ports.comports()]
        
        if SERIAL_PORT not in available_ports:
            # 認識されているポート一覧を見やすく整形
            ports_str = ", ".join(available_ports) if available_ports else "None"
            
            warn_msg = f"Config Warning: Port '{SERIAL_PORT}' is NOT detected on this PC.\nAvailable ports: [{ports_str}].\nPlease check the USB connection or SERIAL_PORT setting."
            messagebox.showwarning("Connection Warning", warn_msg)        
    except Exception as e:
        # この機能がOS環境等で失敗してもアプリの起動は止めない
        print(f"Port check skipped due to error: {e}")
    
    return None

""" Arduinoとの通信を試みる """
def connect_to_arduino():
    global ser
    if is_closing: return

    try:
        ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=1)
        time.sleep(2)
        if not is_closing:
            status_label.config(text=f"Connected to {SERIAL_PORT}. Initializing electrodes...")
        if not initialize_all_devices():
            raise serial.SerialException("Failed to initialize devices during connection.")
        if not is_closing:
            status_label.config(text=f"Connected and Ready.")
            check_serial_input()
            send_heartbeat()

    except serial.SerialException as e:
        if not is_closing: # 終了中はエラーを出さない
            print(f"\n--- CONNECTION ERROR ---\nDetails: {e}\n------------------------\n")
            messagebox.showerror("Connection Error", f"Could not open port {SERIAL_PORT}.\n\nPlease check connection.\n\nError: {e}")
            window.destroy()

""" Arduinoにコマンドを送信し、成功ログを待つ """
def send_command(command_to_send):
    if not (ser and ser.is_open):
        if not is_closing:
            status_label.config(text="Error: Not connected.")
        return False
    
    try:        
        ser.reset_input_buffer() # バッファに残っている古いデータをクリア
        
        ser.write(command_to_send.encode()) # コマンド送信
        print(f"Sent: {command_to_send.strip()}")

        start_time = time.time()
        timeout = 1.0 # デッドラインは1秒

        while (time.time() - start_time) < timeout:
            if ser.in_waiting > 0:
                # データを読み取り、デコードして表示
                line = ser.readline().decode('utf-8', errors='replace').strip()
                
                # "executed"が含まれているかチェック
                if "executed" in line.lower():
                    # print(f"Ack Received: {line}")
                    return True
                
            time.sleep(0.01)

        # タイムアウト
        print(f"Timeout: No 'executed' response for '{command_to_send.strip()}'")
        if not is_closing: # 終了中はエラーを出さない
            status_label.config(text="Communication unstable: No response.")
            messagebox.showwarning("Communication Warning", 
                                   f"Device did not respond (No 'executed' message).\n\nCommand: {command_to_send}")
        return False
    
    except serial.SerialException as e:
        if not is_closing: # 終了中はエラーを出さない
            print(f"\n--- COMMUNICATION ERROR ---\nDetails: {e}\n--------------------\n")
            messagebox.showerror("Communication Error", f"Failed to send command.\nConnection may be lost.\n\nError: {e}")
            status_label.config(text="Disconnected. Please restart the application.")
            disable_all_widgets_on_error()
        return False

"""定期的にHBコマンドを送る"""
def send_heartbeat():
    global ser
    if ser and ser.is_open:
        try:
            ser.write(b"HB\n") # ログを出さない
            window.after(HEARTBEAT_INTERVAL, send_heartbeat) # 次回の予約
        except Exception:
            pass

""" Arduinoからのシリアル入力を監視・表示する """
def check_serial_input():
    if is_closing: return
    if ser and ser.is_open:
        try:
            # 受信データがあるか確認
            while ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='replace').strip()
                if line:
                    print(f"[Arduino] {line}")

                    # 測定終了処理
                    if "MEASUREMENT_END" in line:
                        finish_measurement()
                    
        except Exception as e:
            print(f"Serial Read Error: {e}")
    
    # 100ms後に再実行
    try:
        if window.winfo_exists() and not is_closing:
            window.after(100, check_serial_input)
    except:
        pass

""" 管理下の全デバイス、電極、サーボモータを初期状態(OFF)にする """
def initialize_all_devices():
    if not (ser and ser.is_open): return False

    success = True
    # 電極をすべて切断
    for elec_pin in ELECTRODE_MAP.values():
        if not send_command(f"DO,{elec_pin},0\n"): success = False # DigitalOutput用コマンドは DO,pin,0/1
        time.sleep(0.05)
    # サーボモータをすべてOFF角度へ
    for settings in SERVO_MAP.values():
        servo_pin = settings['pin']
        off_angle = settings['off_angle']
        if not send_command(f"SV,{servo_pin},{off_angle}\n"): success = False # サーボ用コマンドは SV,pin,angle
        time.sleep(0.1)
    # HZ-ProのDIをすべてHIGHへ（Active Lowにするので待機時はHIGH）
    if not send_command(f"DO,{START_PIN},1\n"): success = False
    time.sleep(0.05)
    if not send_command(f"DO,{E_STOP_PIN},1\n"): success = False

    # GUI更新（終了中は行わない）
    if not is_closing:
        try:
            # チェックボックス等状態更新
            for var in elec_check_vars.values(): var.set(0)
            for var in master_elec_check_vars.values(): var.set(0)
            for var in gas_check_vars.values(): var.set(0)
            if estop_var: estop_var.set(0)

            # UIのロック解除、測定開始/エマストボタン状態リセット
            toggle_ui_lock(False)
            if start_button: start_button.config(state=tk.NORMAL, relief=tk.RAISED)
            if estop_widget:
                estop_widget.config(fg="black", font=("Arial", 9, "bold"))

            if 'status_label' in globals() and status_label.winfo_exists():
                status_label.config(text="Device initialization finished.")

        except tk.TclError:
            print("Notice: GUI update skipped (Window closed).")

    print("Device initialization attempt finished.")
    return success

""" 測定中UIをロックする処理 """
def toggle_ui_lock(is_locked): # True：ロック、False：解除
    if is_closing: return

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
    if not (ser and ser.is_open) or is_closing: return

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
    if not (ser and ser.is_open) or is_closing: return

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
    if update_gui and not is_closing:
        action_text = "Connected" if new_state == 1 else "Disconnected"
        status_label.config(text=f"{action_text} {clicked_elec_name}.")
        update_all_master_checkboxes()

""" 親チェックボックスの状態を矛盾がないように更新する """
def update_all_master_checkboxes():
    if is_closing: return
    for cell_name, electrodes_in_cell in CELLS_AND_ELECTRODES.items():
        are_all_electrodes_connected = all(elec_check_vars[elec_name].get() == 1 for elec_name in electrodes_in_cell)
        master_elec_check_vars[cell_name].set(1 if are_all_electrodes_connected else 0)

""" ガスチェックボックスがクリックされたときの処理 """
def on_gas_check_click(clicked_gasline_name, update_gui=True):
    if not (ser and ser.is_open) or is_closing: return

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
    if update_gui and not is_closing:
        action_text = "Opened" if new_state == 1 else "Closed"
        status_label.config(text=f"Gas line {clicked_gasline_name} {action_text}.")

""" 測定開始ボタンが押されたときの処理 """
def start_measurement():
    global is_measuring

    if not (ser and ser.is_open) or is_closing: return

    # Active LowなのでLOWを送ってONにする
    send_command(f"DO,{START_PIN},0\n")
    # UI、測定開始ボタンをロック
    toggle_ui_lock(True)
    start_button.config(state=tk.DISABLED, relief=tk.SUNKEN)
    status_label.config(text="Measurement STARTED. Waiting for manual stop (Press E-STOP).")

    is_measuring = True

""" 測定終了時リセット用共通処理（UIと測定開始ピンを待機状態に戻す） """
def reset_to_ready_state():
    global is_measuring

    if is_closing: return

    is_measuring = False
    
    toggle_ui_lock(False)
    if start_button:
        start_button.config(state=tk.NORMAL, relief=tk.RAISED)
    # 測定開始トリガーピンをHIGHに戻しておく
    if ser and ser.is_open:
        send_command(f"DO,{START_PIN},1\n")

""" 正常に測定が終了したときの処理（Arduinoからの信号でトリガー） """
def finish_measurement():
    if is_closing: return

    if not is_measuring:
        print("Ignored 'MEASUREMENT_END' signal (Not in measuring state).")
        return
    
    reset_to_ready_state() # 共通処理

    status_label.config(text="Measurement COMPLETED. Ready for next run.")
    print("Measurement finished signal received.")

""" エマストボタンが押されたときの処理 """
def on_estop_click():
    if not (ser and ser.is_open) or is_closing: return
    
    # ユーザーが押してONにしたときのみ動作
    if estop_var.get() == 1:
        # Active Lowでパルス送信
        send_command(f"DO,{E_STOP_PIN},0\n")
        estop_widget.config(fg="white", font=("Arial", 9, "bold"))
        status_label.config(text="Measurement ABORTED via E-STOP. Device Reset.")
        window.update() # GUIを強制更新して表示を反映
        time.sleep(0.5)
        send_command(f"DO,{E_STOP_PIN},1\n") 
        
        reset_to_ready_state() # 共通処理
        
        # 固有のUIリセット
        estop_var.set(0)
        estop_widget.config(fg="black", font=("Arial", 9, "bold"))
        status_label.config(text="E-STOP Released. Ready for next measurement.")
    else:
        # 万が一OFF操作された場合も安全のためHIGHを送っておく
        send_command(f"DO,{E_STOP_PIN},1\n")

""" プログラム進行中、エラーの際にGUI上の全ウィジェットを無効化する """
def disable_all_widgets_on_error():
    if is_closing: return
    for widget in all_widgets:
        widget.config(state=tk.DISABLED)
    if start_button: start_button.config(state=tk.DISABLED)

""" 正常にプログラムを終了する """
def on_closing():
    global is_closing

    print("\n--- Closing Application ---")
    is_closing = True

    if ser and ser.is_open:
        print("Resetting devices...")
        initialize_all_devices()

        ser.close()
        print("Serial port closed.")

    window.destroy()
    print("Application closed.")

# --- メインの実行部分 ---

if __name__ == '__main__':
    load_settings()
    generate_maps()

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
        estop_widget = tk.Checkbutton(measurement_frame, text="E-STOP [Esc]", bg="#ffcccc", variable=estop_var, 
                             indicatoron=0, selectcolor="red", 
                             width=20, height=2, fg="black", font=("Arial", 9, "bold"),
                             command=on_estop_click)
        estop_widget.pack(pady=2)

        # リセット関係
        bottom_frame = tk.Frame(window)
        bottom_frame.pack(side=tk.BOTTOM, pady=10, fill=tk.X, padx=10)

        # 初期化ボタン
        initialize_button = tk.Button(bottom_frame, text="Initialize All Devices", command=initialize_all_devices,
                                      width=20, height=2)
        initialize_button.pack(side=tk.LEFT, padx=20)
        all_widgets.append(initialize_button)

        # 終了ボタン
        quit_button = tk.Button(bottom_frame, text="Exit Application", command=on_closing, 
                                width=20, height=2)
        quit_button.pack(side=tk.RIGHT, padx=20)
        all_widgets.append(quit_button)

        # ログ表示のためのラベル
        status_label = tk.Label(window, text="Connecting...", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        status_label.pack(side=tk.BOTTOM, fill=tk.X)
        
        window.protocol("WM_DELETE_WINDOW", on_closing)
        window.after(100, connect_to_arduino)

        window.bind('<Escape>', lambda e: (estop_var.set(1), on_estop_click()))
        
        window.mainloop()