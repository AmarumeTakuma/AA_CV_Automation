import tkinter as tk
from tkinter import messagebox
import serial
import time

# --- ルールブックの定義 ---

# 各電極とArduinoのピン番号の対応
# 接続を変更した場合はここを変更
# 0番と1番ピンは通信用に使われるので使用不可
ELECTRODE_MAP = {
    'Cell A-WE': 2, 'Cell A-CE': 3, 'Cell A-RE': 4,
    'Cell B-WE': 5, 'Cell B-CE': 6, 'Cell B-RE': 7,
}
# 各電極がどのセルに属するかの定義
MAIN_CELLS = {
    'Cell A': ['Cell A-WE', 'Cell A-CE', 'Cell A-RE'],
    'Cell B': ['Cell B-WE', 'Cell B-CE', 'Cell B-RE'],
}
# 同電極のピンが同時に接続されないように設定する排他チャンネル
EXCLUSIVE_CHANNELS = {
    'WE Channel': ['Cell A-WE', 'Cell B-WE'],
    'CE Channel': ['Cell A-CE', 'Cell B-CE'],
    'RE Channel': ['Cell A-RE', 'Cell B-RE'],
}
# 検索を高速化するための逆引き辞書を自動生成
REVERSE_CHANNEL_MAP = {}
for ch_name, elec_names in EXCLUSIVE_CHANNELS.items():
    for elec_name in elec_names:
        REVERSE_CHANNEL_MAP[elec_name] = ch_name

# --- グローバル変数 ---

ser = None
check_vars = {} # 子チェックボックスの状態を管理する辞書
master_check_vars = {} # 親チェックボックスの状態を管理する辞書
all_widgets = [] # GUIの全ウィジェットを管理する

# --- 関数定義 ---

# ELECTRODE_MAPをもとにMAIN_CELLSとEXCLUSIVE_CHANNELSの整合性をチェックする
def validate_configuration():
    all_elec_names = set(ELECTRODE_MAP.keys())
    # MAIN_CELLSの整合性チェック
    for cells_name, elec_names_in_cell in MAIN_CELLS.items():
        for elec_name in elec_names_in_cell:
            if elec_name not in all_elec_names:
                return f"Configuration Error:\nAlias '{elec_name}' in '{cells_name}' not found in ELECTRODE_MAP."
    # EXCLUSIVE_CHANNELSの整合性チェック
    for channel_name, elec_names_in_channel in EXCLUSIVE_CHANNELS.items():
        for elec_name in elec_names_in_channel:
            if elec_name not in all_elec_names:
                return f"Configuration Error:\nAlias '{elec_name}' in '{channel_name}' not found in ELECTRODE_MAP."
    return None

def send_command(command_to_send):
    if not (ser and ser.is_open):
        status_label.config(text="Error: Not connected.")
        return
    try:
        ser.write(command_to_send.encode())
        print(f"Sent: {command_to_send.strip()}")
    except serial.SerialException as e:
        print("\n--- COMMUNICATION ERROR ---")
        print(f"Error while sending command: {command_to_send.strip()}")
        print(f"Details: {e}")
        print("---------------------------\n")
        messagebox.showerror("Communication Error", f"Failed to send command.\nConnection may be lost.\n\nError: {e}")
        status_label.config(text="Disconnected. Please restart the application.")
        disable_all_widgets()

def connect_to_arduino(port="COM5", baudrate=9600):
    global ser
    try:
        ser = serial.Serial(port, baudrate, timeout=1)
        time.sleep(2)
        status_label.config(text=f"Connected to {port}. Initializing electrodes...")
        disconnect_all_electrodes()
        status_label.config(text=f"Connected and Ready.")
    except serial.SerialException as e:
        print("\n--- CONNECTION ERROR ---")
        print(f"Could not open port {port}.")
        print(f"Details: {e}")
        print("------------------------\n")
        messagebox.showerror("Connection Error", f"Could not open port {port}.\n\nPlease check the connection and ensure no other program is using the port.\n\nError: {e}")
        on_closing()

def disconnect_all_electrodes():
    if not (ser and ser.is_open): return

    for pin_number in ELECTRODE_MAP.values():
        send_command(f"{pin_number},0\n")
        time.sleep(0.05)
    for var in check_vars.values(): var.set(0)
    for var in master_check_vars.values(): var.set(0)
    print("All electrodes disconnected.")
    if 'status_label' in globals() and status_label.winfo_exists():
        status_label.config(text="All electrodes disconnected.")

# 一括操作チェックボックスがクリックされたときの処理
def on_master_checkbox_click(cell_name):
    if not (ser and ser.is_open): return

    state = master_check_vars[cell_name].get()
    electrodes_in_cell = MAIN_CELLS[cell_name]
    if state == 1:
        # 他のセルをすべて切断する
        for other_cell_name in MAIN_CELLS:
            if other_cell_name != cell_name:
                for elec_name in MAIN_CELLS[other_cell_name]:
                    if check_vars[elec_name].get() == 1:
                        check_vars[elec_name].set(0)
                        on_check_click(elec_name, display_log=False)
        # このセルをすべて接続する
        for elec_name in electrodes_in_cell:
            if check_vars[elec_name].get() == 0:
                check_vars[elec_name].set(1)
                on_check_click(elec_name, display_log=False)
    else:
        #このセルをすべて切断する
        for elec_name in electrodes_in_cell:
            if check_vars[elec_name].get() == 1:
                check_vars[elec_name].set(0)
                on_check_click(elec_name, display_log=False)
    
    # ログを表示
    action_text = "Connected" if state == 1 else "Disconnected"
    status_label.config(text=f"All electrodes in {cell_name} {action_text}.")
    update_all_master_checkboxes()

# チェックボックスがクリックされたときの処理
def on_check_click(clicked_elec_name, display_log=True):
    if not (ser and ser.is_open): return

    new_state = check_vars[clicked_elec_name].get()
    if new_state == 0:
        # この電極を切断する
        pin_number = ELECTRODE_MAP[clicked_elec_name]
        send_command(f"{pin_number},0\n")
        if display_log:
            status_label.config(text=f"Disconnected {clicked_elec_name}")
    else:
        channel_name = REVERSE_CHANNEL_MAP.get(clicked_elec_name)
        if channel_name:
            for elec_name_in_channel in EXCLUSIVE_CHANNELS[channel_name]:
                if elec_name_in_channel != clicked_elec_name and check_vars[elec_name_in_channel].get() == 1:
                    check_vars[elec_name_in_channel].set(0)
                    send_command(f"{ELECTRODE_MAP[elec_name_in_channel]},0\n")
                    time.sleep(0.05)
        pin_to_connect = ELECTRODE_MAP[clicked_elec_name]
        send_command(f"{pin_to_connect},1\n")
        if display_log:
            status_label.config(text=f"Connected {clicked_elec_name}")

    if display_log:
        update_all_master_checkboxes()

def update_all_master_checkboxes():
    for cell_name, electrodes_in_cell in MAIN_CELLS.items():
        are_all_electrodes_connected = all(check_vars[alias].get() == 1 for alias in electrodes_in_cell)
        master_check_vars[cell_name].set(1 if are_all_electrodes_connected else 0)

def disable_all_widgets():
    for widget in all_widgets:
        widget.config(state=tk.DISABLED)

def on_closing():
    if ser and ser.is_open:
        disconnect_all_electrodes()
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
        print("\n--- CONFIGURATION ERROR ---")
        print(config_error)
        print("---------------------------\n")
        messagebox.showerror("Configuration Error", config_error)
        window.destroy()

    else:
        # GUI作成
        groups_container_frame = tk.Frame(window)
        groups_container_frame.pack(pady=10)

        for cell_name, electrodes_in_cell in MAIN_CELLS.items():
            # セルごとのフレーム
            main_frame = tk.LabelFrame(groups_container_frame, text=cell_name, padx=10, pady=5, font=("Helvetica", 11, "bold"))
            main_frame.pack(side=tk.LEFT, padx=10, pady=5, fill=tk.Y, anchor=tk.N)
            
            # 親チェックボックス
            var_master = tk.IntVar()
            chk_master = tk.Checkbutton(main_frame, text="Connect / Disconnect All", variable=var_master,
                                        command=lambda g=cell_name: on_master_checkbox_click(g))
            chk_master.pack(anchor=tk.W)
            master_check_vars[cell_name] = var_master
            all_widgets.append(chk_master)

            # 子チェックボックス
            for elec_name in electrodes_in_cell:
                electrode_type = elec_name.split('-')[1]
                var = tk.IntVar(value=0)
                checkbox = tk.Checkbutton(main_frame, text=electrode_type, variable=var,
                                            command=lambda a=elec_name: on_check_click(a))
                checkbox.pack(anchor=tk.W, padx=10)
                check_vars[elec_name] = var
                all_widgets.append(checkbox)

        # 全切断ボタン
        disconnect_button = tk.Button(window, text="Disconnect All Electrodes", command=disconnect_all_electrodes)
        disconnect_button.pack(pady=10)
        all_widgets.append(disconnect_button)

        # ログ表示のためのラベル
        status_label = tk.Label(window, text="Connecting...", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        status_label.pack(side=tk.BOTTOM, fill=tk.X)
        
        window.protocol("WM_DELETE_WINDOW", on_closing)
        window.after(100, connect_to_arduino)
        window.mainloop()