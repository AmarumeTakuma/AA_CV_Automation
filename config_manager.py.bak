import json
import os
import sys

class ConfigManager:
    def __init__(self, filename="settings.json"):
        self.filename = filename
        
        # 設定値

        # Arduinoが接続されているCOMポートとボーレート
        self.serial_port = ""
        self.baudrate = 9600

        # Arduinoのピン番号の対応
        self.di1_output_pin = -1
        self.estop_pin = -1
        self.done_pin = -1
        self.cell_definitions = {}
        self.servo_map = {}

        # 安全のための制約
        self.required_electrodes = set()
        self.max_pin_number = 70
        self.prohibited_pins = []
        self.min_angle_diff = 5
        self.watchdog_timeout = 3000
        self.heartbeat_interval = 1000
        self.standard_baudrates = []

        # 自動生成される辞書
        self.electrode_map = {} # 各電極とピンの対応（例: 'Cell A-WE': 2）
        self.cells_and_electrodes = {} # 各電極がどのセルに属するかの定義（例: 'Cell A': ['Cell A-WE', 'Cell A-CE', 'Cell A-RE']）
        self.elec_exclusive_channels = {} # 同種の電極のピンが同時に接続されないように設定する排他チャンネル（例: 'WE Channel': ['Cell A-WE', 'Cell B-WE'],）
        self.gas_exclusive_channels = {} # ガスラインの排他チャンネル（例: 'Gas Channel': ['Gas Line A', 'Gas Line B']）
        self.reverse_elec_exclusive = {} # 電極排他チャンネルの逆引き辞書（例: 'Cell A-WE': 'WE Channel'）
        self.reverse_gas_exclusive = {} # ガスライン排他チャンネルの逆引き辞書（例: 'Gas Line A': 'Gas Channel'）

        # 読み込み実行
        self.load_settings()
        self.generate_maps()

    def get_app_path(self):
        """ 実行ファイル（main.pyまたはexe）と同じ場所にあるJSONを探してパスを取得する関数 """
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable) # .exe
        return os.path.dirname(os.path.abspath(__file__)) # .py

    def load_settings(self):
        """ settings.jsonから設定を読み込む関数 """
        path = os.path.join(self.get_app_path(), self.filename)
        
        if not os.path.exists(path):
            raise FileNotFoundError(f"Configuration file not found:\n{path}")

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Connection
            conn = data.get("connection", {})
            self.serial_port = conn.get("port", "") # なかった場合、予測できないのでとりあえず空文字にして後でエラー
            self.baudrate = conn.get("baudrate", 9600) # なかった場合とりあえず一般的な値へ

            # Pin Assignments（なかった場合無効化（-1））
            pins = data.get("pins", {})
            self.di1_output_pin = pins.get("di1_output", -1)
            self.estop_pin = pins.get("estop", -1)
            self.done_pin = pins.get("done", -1)

            # Maps（なかった場合、空辞書にして後のループ処理で落ちないように）
            # JSON構造: "Cell A": {"WE": 2, "CE": 3...}, "Gas Line A": {"pin": 5, "on_angle": 90...}
            self.cell_definitions = data.get("cells", {})
            self.servo_map = data.get("servos", {})

            # Safety Settings（なかった場合とりあえず一般的な値へ）
            safe = data.get("safety", {})
            self.prohibited_pins = safe.get("prohibited_pins", [])
            self.min_angle_diff = safe.get("min_angle_diff", 5)
            self.watchdog_timeout = safe.get("watchdog_timeout_ms", 3000)
            self.heartbeat_interval = max(100, int(self.watchdog_timeout / 3)) # # タイムアウトの 1/3 の間隔で送信（最低100msは確保）

            # Validation Settings
            val = data.get("validation", {})
            self.required_electrodes = set(val.get("required_electrodes", ["WE", "CE", "RE"]))

            # System Limits
            limits = data.get("system_limits", {})
            self.max_pin_number = limits.get("max_pin_number", 70)
            self.standard_baudrates = limits.get("allowed_baudrates", [9600])
            
            print(f"Loaded configuration: {path}")

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format:\n{e}")
        except Exception as e:
            raise RuntimeError(f"Error loading settings:\n{e}")

    def generate_maps(self):
        """ 読み込んだ設定をもとに、排他チャンネルや逆引き辞書を生成する関数 """
        # 初期化
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
                elec_name = f"{cell_name}-{elec_type}" # セルに属するように電極名を作成 (例: "Cell A-WE")
                self.electrode_map[elec_name] = pin
                elec_list.append(elec_name) # CELLS_AND_ELECTRODES のためのリスト作成
                
                # 排他チャンネルへの割り振り (例: "WE Channel" にすべてのWEをまとめる）
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

        # 逆引き辞書生成
        for ch, names in self.elec_exclusive_channels.items():
            for name in names: self.reverse_elec_exclusive[name] = ch
        for ch, names in self.gas_exclusive_channels.items():
            for name in names: self.reverse_gas_exclusive[name] = ch
            
        print("Internal maps generated.")

    def validate(self):
        """ ルールブックの整合性をチェックする関数 """
        # 設定が空ならエラー
        if not self.cell_definitions and not self.servo_map:
            return "Config Error: No Cells and No Gas Lines defined.\nPlease configure CELL_DEFINITIONS or SERVO_MAP."

        # 電極チェック
        for cell_name, pins in self.cell_definitions.items():
            defined_types = set(pins.keys())
            missing = self.required_electrodes - defined_types
            if missing:
                return f"Config Error: '{cell_name}' is missing required electrodes: {list(missing)}.\nRequired per settings: {list(self.required_electrodes)}"

        # サーボチェック
        for name, settings in self.servo_map.items():
            if settings.get('pin', -1) < 0: continue
            # オンオフ角度が存在することをチェック
            if 'on_angle' not in settings or 'off_angle' not in settings:
                return f"Config Error: Gas line '{name}' in GAS_SERVO_MAP is missing essential angles."
            # 差が小さすぎないことをチェック
            angle_diff = abs(settings['on_angle'] - settings['off_angle'])
            if angle_diff < self.min_angle_diff:
                return f"Config Warning: Gas line '{name}' angles are too close (Diff: {angle_diff}°).\nMechanical backlash may prevent reliable switching.\nRecommended difference is > {self.min_angle_diff}°."
            # 'angle'が含まれるすべての角度が適切かチェック
            for key, value in settings.items():
                if 'angle' in key:
                    if not (isinstance(value, int) and 0 <= value <= 180):
                        return f"Config Error: '{key}' for '{name}' must be an integer between 0 and 180."
        # ガスラインに、メンバーが1つだけのグループがないかチェック（グループ名のタイプミスを検知）
        for group_name, members in self.gas_exclusive_channels.items():
            if len(members) < 2:
                return f"Safety Warning: Gas Group '{group_name}' has only 1 member ({members}).\nExclusive control requires at least 2 members.\nCheck for typos in 'group' name in SERVO_MAP."

        # ピン重複チェック
        pin_usage = {}
        def check_pin(pin, user_name):
            if pin < 0: return None
            # 重複
            if pin in pin_usage:
                return f"Config Error: Pin {pin} is duplicated.\nUsed by '{pin_usage[pin]}' and '{user_name}'."
            pin_usage[pin] = user_name
            # 禁止ピン
            if pin in self.prohibited_pins:
                return f"Safety Error: Pin {pin} is a RESERVED PIN (Serial/LED).\nUsed by '{user_name}'."
            if pin > self.max_pin_number:
                return f"Config Error: Pin {pin} exceeds MAX ({self.max_pin_number})."
            return None

        for name, pin in self.electrode_map.items(): 
            if e := check_pin(pin, name): return e
        for name, settings in self.servo_map.items(): 
            if e := check_pin(settings.get('pin', -1), name): return e
        
        if e := check_pin(self.di1_output_pin, "DI1 Output Pin"): return e
        if e := check_pin(self.estop_pin, "E-Stop Pin"): return e
        if e := check_pin(self.done_pin, "Done Pin"): return e

        # ボーレートの標準値チェック（警告）
        if self.standard_baudrates and self.baudrate not in self.standard_baudrates:
            print(f"Warning: Baudrate {self.baudrate} not in allowed list.")

        return None