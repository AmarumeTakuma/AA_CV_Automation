import tkinter as tk
from tkinter import messagebox
import serial
import time

# --- 1. ルールブックの定義 (ここを編集して拡張) ---
PIN_MAP = {
    'A-Pin1': 2, 'A-Pin2': 3, 'A-Pin3': 6,
    'B-Pin1': 4, 'B-Pin2': 5, 'B-Pin3': 7,
    'C-Pin1': 8, 'C-Pin2': 9, 'C-Pin3': 11,
}
MAIN_GROUPS = {
    'Group A': ['A-Pin1', 'A-Pin2', 'A-Pin3'],
    'Group B': ['B-Pin1', 'B-Pin2', 'B-Pin3'],
    'Group C': ['C-Pin1', 'C-Pin2', 'C-Pin3'],
}
EXCLUSIVE_CHANNELS = {
    'Channel 1': ['A-Pin1', 'B-Pin1', 'C-Pin1'],
    'Channel 2': ['A-Pin2', 'B-Pin2', 'C-Pin2'],
    'Channel 3': ['A-Pin3', 'B-Pin3', 'C-Pin3'],
}

# --- これ以降のプログラム本体は変更不要 ---

# --- グローバル変数 ---
ser = None
check_vars = {}
master_check_vars = {}

# --- 関数定義 ---
def connect_to_arduino(port="COM5", baudrate=9600):
    global ser
    try:
        ser = serial.Serial(port, baudrate, timeout=1)
        time.sleep(2)
        status_label.config(text=f"Connected to {port}. Initializing...")
        turn_all_pins_off()
        status_label.config(text=f"Connected and Ready.")
    except serial.SerialException as e:
        messagebox.showerror("Connection Error", f"Failed to open port {port}:\n{e}")

def turn_all_pins_off():
    if not (ser and ser.is_open): return
    for pin_number in PIN_MAP.values():
        ser.write(f"{pin_number},0\n".encode())
        time.sleep(0.05)
    for var in check_vars.values(): var.set(0)
    for var in master_check_vars.values(): var.set(0)
    print("All pins turned OFF.")
    status_label.config(text="All pins turned OFF.")

def on_master_checkbox_click(group_name):
    if not (ser and ser.is_open): return
    state = master_check_vars[group_name].get()
    pins_in_group = MAIN_GROUPS[group_name]
    if state == 1:
        for channel_name, pins_in_channel in EXCLUSIVE_CHANNELS.items():
            for alias in pins_in_channel:
                if alias in pins_in_group:
                    if check_vars[alias].get() == 0:
                        check_vars[alias].set(1)
                        on_check_click(alias)
                    break
    else:
        for alias in pins_in_group:
            if check_vars[alias].get() == 1:
                check_vars[alias].set(0)
                on_check_click(alias)

def on_check_click(clicked_alias):
    if not (ser and ser.is_open): return
    new_state = check_vars[clicked_alias].get()
    if new_state == 0:
        pin_number = PIN_MAP[clicked_alias]
        ser.write(f"{pin_number},0\n".encode())
        status_label.config(text=f"Set {clicked_alias} to OFF")
    else:
        channel_name = find_channel_for_alias(clicked_alias)
        if channel_name:
            for alias_in_channel in EXCLUSIVE_CHANNELS[channel_name]:
                if alias_in_channel != clicked_alias and check_vars[alias_in_channel].get() == 1:
                    check_vars[alias_in_channel].set(0)
                    ser.write(f"{PIN_MAP[alias_in_channel]},0\n".encode())
                    time.sleep(0.05)
        pin_to_turn_on = PIN_MAP[clicked_alias]
        ser.write(f"{pin_to_turn_on},1\n".encode())
        status_label.config(text=f"Set {clicked_alias} to ON")
    update_all_master_checkboxes()

def find_channel_for_alias(target_alias):
    for ch_name, aliases in EXCLUSIVE_CHANNELS.items():
        if target_alias in aliases:
            return ch_name
    return None

def update_all_master_checkboxes():
    for group_name, pins_in_group in MAIN_GROUPS.items():
        are_all_pins_on = all(check_vars[alias].get() == 1 for alias in pins_in_group)
        master_check_vars[group_name].set(1 if are_all_pins_on else 0)

def on_closing():
    if ser and ser.is_open:
        turn_all_pins_off()
        ser.close()
    window.destroy()

# --- GUIの組み立て ---
window = tk.Tk()
window.title("Scalable Hybrid Controller")

for group_name, pins_in_group in MAIN_GROUPS.items():
    main_frame = tk.LabelFrame(window, text=group_name, padx=10, pady=5, font=("Helvetica", 11, "bold"))
    main_frame.pack(padx=10, pady=5, fill=tk.X)
    var_master = tk.IntVar()
    chk_master = tk.Checkbutton(main_frame, text="All ON / OFF", variable=var_master,
                                command=lambda g=group_name: on_master_checkbox_click(g))
    chk_master.pack(anchor=tk.W)
    master_check_vars[group_name] = var_master
    for channel_name, pins_in_channel in EXCLUSIVE_CHANNELS.items():
        channel_has_pins_from_group = any(p in pins_in_group for p in pins_in_channel)
        if channel_has_pins_from_group:
            channel_frame = tk.LabelFrame(main_frame, text=channel_name, padx=10, pady=5)
            channel_frame.pack(padx=5, pady=2, fill=tk.X)
            for alias in pins_in_channel:
                if alias in pins_in_group:
                    var = tk.IntVar(value=0)
                    checkbox = tk.Checkbutton(channel_frame, text=alias, variable=var,
                                              command=lambda a=alias: on_check_click(a))
                    checkbox.pack(anchor=tk.W)
                    check_vars[alias] = var

off_button = tk.Button(window, text="Turn All OFF", command=turn_all_pins_off)
off_button.pack(pady=10)
status_label = tk.Label(window, text="Connecting...", bd=1, relief=tk.SUNKEN, anchor=tk.W)
status_label.pack(side=tk.BOTTOM, fill=tk.X)

# --- プログラムの実行 ---
window.protocol("WM_DELETE_WINDOW", on_closing)
window.after(100, connect_to_arduino)
window.mainloop()