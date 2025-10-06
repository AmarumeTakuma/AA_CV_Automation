import tkinter as tk
from tkinter import messagebox
import serial
import time

# --- ルールブックの定義 ---
ELECTRODE_MAP = {
    'Cell A-WE': 2, 'Cell A-CE': 3, 'Cell A-RE': 4 ,
    'Cell B-WE': 5, 'Cell B-CE': 6, 'Cell B-RE': 7,
}
MAIN_CELLS = {
    'Cell A': ['Cell A-WE', 'Cell A-CE', 'Cell A-RE'],
    'Cell B': ['Cell B-WE', 'Cell B-CE', 'Cell B-RE'],
}
EXCLUSIVE_CHANNELS = {
    'WE Channel': ['Cell A-WE', 'Cell B-WE'],
    'CE Channel': ['Cell A-CE', 'Cell B-CE'],
    'RE Channel': ['Cell A-RE', 'Cell B-RE'],
}

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
        status_label.config(text=f"Connected to {port}. Initializing electrodes...")
        disconnect_all_electrodes()
        status_label.config(text=f"Connected and Ready.")
    except serial.SerialException as e:
        messagebox.showerror("Connection Error", f"Failed to open port {port}:\n{e}")

def disconnect_all_electrodes():
    if not (ser and ser.is_open): return
    for pin_number in ELECTRODE_MAP.values():
        ser.write(f"{pin_number},0\n".encode())
        time.sleep(0.05)
    for var in check_vars.values(): var.set(0)
    for var in master_check_vars.values(): var.set(0)
    print("All electrodes disconnected.")
    status_label.config(text="All electrodes disconnected.")

def on_master_checkbox_click(cell_name):
    if not (ser and ser.is_open): return
    state = master_check_vars[cell_name].get()
    electrodes_in_cell = MAIN_CELLS[cell_name]
    if state == 1:
        for channel_name, electrodes_in_channel in EXCLUSIVE_CHANNELS.items():
            for alias in electrodes_in_channel:
                if alias in electrodes_in_cell:
                    if check_vars[alias].get() == 0:
                        check_vars[alias].set(1)
                        on_check_click(alias, update_master=False)
                    break
    else:
        for alias in electrodes_in_cell:
            if check_vars[alias].get() == 1:
                check_vars[alias].set(0)
                on_check_click(alias, update_master=False)
    
    action_text = "Connected" if state == 1 else "Disconnected"
    status_label.config(text=f"All electrodes in {cell_name} {action_text}.")
    update_all_master_checkboxes()

def on_check_click(clicked_alias, update_master=True):
    if not (ser and ser.is_open): return
    new_state = check_vars[clicked_alias].get()
    if new_state == 0:
        pin_number = ELECTRODE_MAP[clicked_alias]
        ser.write(f"{pin_number},0\n".encode())
        if update_master:
            status_label.config(text=f"Disconnected {clicked_alias}")
    else:
        channel_name = find_channel_for_alias(clicked_alias)
        if channel_name:
            for alias_in_channel in EXCLUSIVE_CHANNELS[channel_name]:
                if alias_in_channel != clicked_alias and check_vars[alias_in_channel].get() == 1:
                    check_vars[alias_in_channel].set(0)
                    ser.write(f"{ELECTRODE_MAP[alias_in_channel]},0\n".encode())
                    time.sleep(0.05)
        pin_to_connect = ELECTRODE_MAP[clicked_alias]
        ser.write(f"{pin_to_connect},1\n".encode())
        if update_master:
            status_label.config(text=f"Connected {clicked_alias}")
    if update_master:
        update_all_master_checkboxes()

def find_channel_for_alias(target_alias):
    for ch_name, aliases in EXCLUSIVE_CHANNELS.items():
        if target_alias in aliases:
            return ch_name
    return None

def update_all_master_checkboxes():
    for cell_name, electrodes_in_cell in MAIN_CELLS.items():
        are_all_electrodes_connected = all(check_vars[alias].get() == 1 for alias in electrodes_in_cell)
        master_check_vars[cell_name].set(1 if are_all_electrodes_connected else 0)

def on_closing():
    if ser and ser.is_open:
        disconnect_all_electrodes()
        ser.close()
    window.destroy()

# --- GUIの組み立て ---
window = tk.Tk()
window.title("Electrode Controller")

groups_container_frame = tk.Frame(window)
groups_container_frame.pack(pady=10)

for cell_name, electrodes_in_cell in MAIN_CELLS.items():
    main_frame = tk.LabelFrame(groups_container_frame, text=cell_name, padx=10, pady=5, font=("Helvetica", 11, "bold"))
    main_frame.pack(side=tk.LEFT, padx=10, pady=5, fill=tk.Y, anchor=tk.N)
    
    var_master = tk.IntVar()
    chk_master = tk.Checkbutton(main_frame, text="Connect / Disconnect All", variable=var_master,
                                command=lambda g=cell_name: on_master_checkbox_click(g))
    chk_master.pack(anchor=tk.W)
    master_check_vars[cell_name] = var_master

    for alias in electrodes_in_cell:
        electrode_type = alias.split('-')[1]
        var = tk.IntVar(value=0)
        checkbox = tk.Checkbutton(main_frame, text=electrode_type, variable=var,
                                    command=lambda a=alias: on_check_click(a))
        checkbox.pack(anchor=tk.W, padx=10)
        check_vars[alias] = var

disconnect_button = tk.Button(window, text="Disconnect All Electrodes", command=disconnect_all_electrodes)
disconnect_button.pack(pady=10)
status_label = tk.Label(window, text="Connecting...", bd=1, relief=tk.SUNKEN, anchor=tk.W)
status_label.pack(side=tk.BOTTOM, fill=tk.X)

# --- プログラムの実行 ---
window.protocol("WM_DELETE_WINDOW", on_closing)
window.after(100, connect_to_arduino)
window.mainloop()