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

        # GPIO ピン（Arduino 直結）
        self.di1_output_pin = -1
        self.estop_pin = -1
        self.done_pin = -1

        # PCA9685 設定
        self.pca_address = 0x40
        self.pca_frequency = 50

        # PCA9685 経由の制御マップ
        self.pca_relay_map = {}  # 'Cell A-WE': 0, etc.
        self.pca_servo_map = {}  # 'Gas Line A': {'channel': 9, 'on_angle': 90, ...}

        # 安全のための制約
        self.required_electrodes = set()
        self.max_pca_channels = 16
        self.min_angle_diff = 5
        self.watchdog_timeout = 3000
        self.heartbeat_interval = 1000
        self.standard_baudrates = []

        # 自動生成される辞書
        self.cells_and_electrodes = {}  # セルと電極の関係
        self.elec_exclusive_channels = {}  # 同種の電極排他チャネル
        self.gas_exclusive_channels = {}  # ガスラインの排他チャネル
        self.reverse_elec_exclusive = {}  # 電極の逆引き
        self.reverse_gas_exclusive = {}  # ガスラインの逆引き

        # 読み込み実行
        self.load_settings()
        self.generate_maps()

    def get_app_path(self):
        """ 実行ファイル（main.pyまたはexe）と同じ場所にあるJSONを探してパスを取得する関数 """
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

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
            self.serial_port = conn.get("port", "")
            self.baudrate = conn.get("baudrate", 9600)

            # GPIO Pins
            gpio = data.get("gpio_pins", {})
            self.di1_output_pin = gpio.get("di1_output", -1)
            self.estop_pin = gpio.get("estop", -1)
            self.done_pin = gpio.get("done", -1)

            # PCA9685 Configuration
            pca_conf = data.get("pca9685", {})
            self.pca_address = pca_conf.get("address", 0x40)
            self.pca_frequency = pca_conf.get("frequency", 50)

            # PCA9685 Relays and Servos
            self.pca_relay_definitions = data.get("pca_relays", {})
            self.pca_servo_definitions = data.get("pca_servos", {})

            # Safety Settings
            safe = data.get("safety", {})
            self.min_angle_diff = safe.get("min_angle_diff", 5)
            self.watchdog_timeout = safe.get("watchdog_timeout_ms", 3000)
            self.heartbeat_interval = max(100, int(self.watchdog_timeout / 3))

            # Validation Settings
            val = data.get("validation", {})
            self.required_electrodes = set(val.get("required_electrodes", ["WE", "CE", "RE"]))

            # System Limits
            limits = data.get("system_limits", {})
            self.max_pca_channels = limits.get("max_pca_channels", 16)
            self.standard_baudrates = limits.get("allowed_baudrates", [9600])
            
            print(f"Loaded configuration: {path}")

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format:\n{e}")
        except Exception as e:
            raise RuntimeError(f"Error loading settings:\n{e}")

    def generate_maps(self):
        """ 読み込んだ設定をもとに、排他チャンネルや逆引き辞書を生成する関数 """
        # 初期化
        self.pca_relay_map = {}
        self.pca_servo_map = {}
        self.cells_and_electrodes = {}
        self.elec_exclusive_channels = {}
        self.gas_exclusive_channels = {}
        self.reverse_elec_exclusive = {}
        self.reverse_gas_exclusive = {}

        # PCA リレーマップの生成（セル毎の電極チャネル）
        for cell_name, pins in self.pca_relay_definitions.items():
            elec_list = []
            for elec_type, channel in pins.items():
                if channel < 0:
                    continue
                elec_name = f"{cell_name}-{elec_type}"
                self.pca_relay_map[elec_name] = channel
                elec_list.append(elec_name)

                # 排他チャンネルへの割り振り（同種の電極は同時オン禁止）
                ch_name = f"{elec_type} Channel"
                if ch_name not in self.elec_exclusive_channels:
                    self.elec_exclusive_channels[ch_name] = []
                self.elec_exclusive_channels[ch_name].append(elec_name)

            self.cells_and_electrodes[cell_name] = elec_list

        # PCA サーボマップの生成
        for name, props in self.pca_servo_definitions.items():
            if props.get('channel', -1) < 0:
                continue
            self.pca_servo_map[name] = props

            # ガスラインの排他チャンネル
            if 'group' in props:
                grp = props['group']
                if grp not in self.gas_exclusive_channels:
                    self.gas_exclusive_channels[grp] = []
                self.gas_exclusive_channels[grp].append(name)

        # 逆引き辞書生成
        for ch, names in self.elec_exclusive_channels.items():
            for name in names:
                self.reverse_elec_exclusive[name] = ch
        for ch, names in self.gas_exclusive_channels.items():
            for name in names:
                self.reverse_gas_exclusive[name] = ch

        print("Internal maps generated.")
        # --- Backwards compatibility ---
        # Provide `servo_map` with original key names (`pin`) so existing UI code still works.
        self.servo_map = {}
        for name, props in self.pca_servo_map.items():
            # copy props and expose 'pin' alias for 'channel'
            p = dict(props)
            if 'channel' in p:
                p['pin'] = p['channel']
            self.servo_map[name] = p

        # Provide `electrode_map` alias for legacy code (maps 'Cell A-WE' -> channel)
        self.electrode_map = dict(self.pca_relay_map)

    def validate(self):
        """ ルールブックの整合性をチェックする関数 """
        # 設定が空ならエラー
        if not self.pca_relay_definitions and not self.pca_servo_definitions:
            return "Config Error: No Cells and No Gas Lines defined."

        # GPIO ピンチェック
        if not self.serial_port:
            return "Config Error: Serial port not configured."

        # 電極チェック
        for cell_name, pins in self.pca_relay_definitions.items():
            defined_types = set(pins.keys())
            missing = self.required_electrodes - defined_types
            if missing:
                return f"Config Error: '{cell_name}' is missing required electrodes: {list(missing)}."

        # サーボチェック
        for name, settings in self.pca_servo_definitions.items():
            if settings.get('channel', -1) < 0:
                continue
            if 'on_angle' not in settings or 'off_angle' not in settings:
                return f"Config Error: Gas line '{name}' is missing essential angles."
            
            angle_diff = abs(settings['on_angle'] - settings['off_angle'])
            if angle_diff < self.min_angle_diff:
                return f"Config Warning: Gas line '{name}' angles are too close (Diff: {angle_diff}°)."
            
            for key, value in settings.items():
                if 'angle' in key:
                    if not (isinstance(value, int) and 0 <= value <= 180):
                        return f"Config Error: '{key}' for '{name}' must be between 0-180."

        # ガスグループチェック
        for group_name, members in self.gas_exclusive_channels.items():
            if len(members) < 2:
                return f"Safety Warning: Gas Group '{group_name}' has only 1 member."

        # チャネル重複チェック
        channel_usage = {}
        
        def check_channel(channel, user_name):
            if channel < 0:
                return None
            if channel in channel_usage:
                return f"Config Error: PCA channel {channel} is duplicated (used by '{channel_usage[channel]}' and '{user_name}')."
            if channel >= self.max_pca_channels:
                return f"Config Error: PCA channel {channel} exceeds MAX ({self.max_pca_channels})."
            channel_usage[channel] = user_name
            return None

        for name, channel in self.pca_relay_map.items():
            if e := check_channel(channel, name):
                return e
        for name, settings in self.pca_servo_map.items():
            if e := check_channel(settings.get('channel', -1), name):
                return e

        # ボーレートチェック
        if self.standard_baudrates and self.baudrate not in self.standard_baudrates:
            print(f"Warning: Baudrate {self.baudrate} not in allowed list.")

        return None
