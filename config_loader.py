import json
import os
import sys
from tkinter import messagebox

class ConfigManager:
    def __init__(self, filename="settings.json"):
        self.filename = filename
        
        # 設定値

        # Arduinoが接続されているCOMポートとボーレート
        self.serial_port = ""
        self.baudrate = 9600

        # システムピン
        self.start_pin = -1
        self.estop_pin = -1
        self.done_pin = -1

        self.cell_definitions = {}
        self.servo_map = {}

        self.required_electrodes = set()
        self.max_pin_number = 70
        self.prohibited_pins = []
        self.min_angle_diff = 5
        self.watchdog_timeout = 3000
        self.heartbeat_interval = 1000
        self.standard_baudrates = []

        # 自動生成される辞書
        self.electrode_map = {}
        self.cells_and_electrodes = {}
        self.elec_exclusive_channels = {}
        self.gas_exclusive_channels = {}
        self.reverse_elec_exclusive = {}
        self.reverse_gas_exclusive = {}

        # 読み込み実行
        self.load_settings()
        self.generate_maps()

    def get_app_path(self):
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

    def load_settings(self):
        path = os.path.join(self.get_app_path(), self.filename)
        
        if not os.path.exists(path):
            messagebox.showerror("Configuration Error", f"Configuration file not found:\n{path}")
            sys.exit(1)

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            conn = data.get("connection", {})
            self.serial_port = conn.get("port", "")
            self.baudrate = conn.get("baudrate", 9600)

            pins = data.get("pins", {})
            self.start_pin = pins.get("start", -1)
            self.estop_pin = pins.get("estop", -1)
            self.done_pin = pins.get("done", -1)

            self.cell_definitions = data.get("cells", {})
            self.servo_map = data.get("servos", {})

            safe = data.get("safety", {})
            self.prohibited_pins = safe.get("prohibited_pins", [])
            self.min_angle_diff = safe.get("min_angle_diff", 5)
            self.watchdog_timeout = safe.get("watchdog_timeout_ms", 3000)
            self.heartbeat_interval = max(100, int(self.watchdog_timeout / 3))

            val = data.get("validation", {})
            self.required_electrodes = set(val.get("required_electrodes", ["WE", "CE", "RE"]))

            limits = data.get("system_limits", {})
            self.max_pin_number = limits.get("max_pin_number", 70)
            self.standard_baudrates = limits.get("allowed_baudrates", [9600])
            
            print(f"Loaded configuration: {path}")

        except Exception as e:
            messagebox.showerror("Config Error", f"Error loading settings:\n{e}")
            sys.exit(1)

    def generate_maps(self):
        # 毎回初期化
        self.electrode_map = {}
        self.cells_and_electrodes = {}
        self.elec_exclusive_channels = {}
        self.gas_exclusive_channels = {}
        self.reverse_elec_exclusive = {}
        self.reverse_gas_exclusive = {}

        # 電極関係
        for cell_name, pins in self.cell_definitions.items():
            elec_list = []
            for elec_type, pin in pins.items():
                if pin < 0: continue
                elec_name = f"{cell_name}-{elec_type}"
                self.electrode_map[elec_name] = pin
                elec_list.append(elec_name)
                
                ch_name = f"{elec_type} Channel"
                if ch_name not in self.elec_exclusive_channels:
                    self.elec_exclusive_channels[ch_name] = []
                self.elec_exclusive_channels[ch_name].append(elec_name)
            self.cells_and_electrodes[cell_name] = elec_list

        # サーボ関係
        for name, props in self.servo_map.items():
            if props.get('pin', -1) < 0: continue
            if 'group' in props:
                grp = props['group']
                if grp not in self.gas_exclusive_channels:
                    self.gas_exclusive_channels[grp] = []
                self.gas_exclusive_channels[grp].append(name)

        # 逆引き生成
        for ch, names in self.elec_exclusive_channels.items():
            for name in names: self.reverse_elec_exclusive[name] = ch
        for ch, names in self.gas_exclusive_channels.items():
            for name in names: self.reverse_gas_exclusive[name] = ch
            
        print("Internal maps generated.")

    def validate(self):
        if not self.cell_definitions and not self.servo_map:
            return "Config Error: No Cells and No Gas Lines defined."

        # 電極チェック
        for cell_name, pins in self.cell_definitions.items():
            defined_types = set(pins.keys())
            missing = self.required_electrodes - defined_types
            if missing:
                return f"Config Error: '{cell_name}' missing: {list(missing)}"

        # サーボチェック
        for name, settings in self.servo_map.items():
            if settings.get('pin', -1) < 0: continue
            if 'on_angle' not in settings or 'off_angle' not in settings:
                return f"Config Error: '{name}' missing angles."
            if abs(settings['on_angle'] - settings['off_angle']) < self.min_angle_diff:
                return f"Config Warning: '{name}' angles too close."

        # ピン重複チェック
        pin_usage = {}
        def check_pin(pin, user_name):
            if pin < 0: return None
            if pin in pin_usage:
                return f"Config Error: Pin {pin} duplicated ({pin_usage[pin]}, {user_name})"
            pin_usage[pin] = user_name
            if pin in self.prohibited_pins: return f"Safety Error: Pin {pin} is PROHIBITED."
            if pin > self.max_pin_number: return f"Config Error: Pin {pin} > MAX."
            return None

        for n, p in self.electrode_map.items(): 
            if e := check_pin(p, n): return e
        for n, s in self.servo_map.items(): 
            if e := check_pin(s.get('pin', -1), n): return e
        
        if e := check_pin(self.start_pin, "Start Pin"): return e
        if e := check_pin(self.estop_pin, "E-Stop Pin"): return e
        if e := check_pin(self.done_pin, "Done Pin"): return e

        if self.standard_baudrates and self.baudrate not in self.standard_baudrates:
            print(f"Warning: Baudrate {self.baudrate} not in allowed list.")

        return None