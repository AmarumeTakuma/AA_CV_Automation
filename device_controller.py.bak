import serial
import serial.tools.list_ports
import time

class DeviceCommunicationError(Exception):
    """通信エラー（切断、ポートオープン失敗など）"""
    pass

class DeviceTimeoutError(Exception):
    """コマンド応答なし（タイムアウト）"""
    pass

class ArduinoDevice:
    def __init__(self, config):
        self.config = config  # ConfigManagerのインスタンスを受け取る
        self.ser = None
        self.is_connected = False

    def check_port_available(self):
        """
        設定されたCOMポートがPCに認識されているかチェックする
        戻り値: (bool: 存在するかどうか, list: 現在認識されているポート名のリスト)
        """
        try:
            available_ports = [p.device for p in serial.tools.list_ports.comports()] # PC上の全ポートを取得
            is_available = self.config.serial_port in available_ports
            return is_available, available_ports
        except Exception as e: # OSの権限エラー等で確認できない場合は、チェックスキップ(True)として先に進める
            print(f"Port check skipped due to error: {e}")
            return True, []

    def connect(self):
        """ Arduinoとのシリアル通信を開始する """
        try:
            self.ser = serial.Serial(self.config.serial_port, self.config.baudrate, timeout=1)
            time.sleep(2)  # Arduinoの自動リセット完了を待つ
            self.is_connected = True
            return True
        except serial.SerialException as e:
            msg = f"Could not open {self.config.serial_port}: {e}"
            print(f"Connection Error: {msg}")
            raise DeviceCommunicationError(msg)

    def close(self):
        """ 通信を安全に閉じる """
        if self.ser and self.ser.is_open:
            try:
                self.initialize_devices()  # 安全のため、ポートを閉じる前に全ピンを初期化
            except Exception as e:
                # 終了時の初期化エラーは無視して、ポート自体は確実に閉じる
                print(f"Warning: Device initialization during close failed: {e}")
            self.ser.close()
        self.is_connected = False

    def send_command(self, command):
        """ コマンドを送信し、'executed' の応答(Ack)を待つ """
        if not (self.ser and self.ser.is_open):
            msg = f"Command '{command.strip()}' failed: Device not connected."
            print(f"Communication Error: {msg}")
            raise DeviceCommunicationError(msg)
        
        try:        
            self.ser.reset_input_buffer()

            # コマンド送信
            self.ser.write(command.encode())
            print(f"Sent: {command.strip()}")

            # 簡易ハンドシェイク（タイムアウト1.0秒）
            start_time = time.time()
            timeout = 1.0
            while (time.time() - start_time) < timeout:
                if self.ser.in_waiting > 0:
                    line = self.ser.readline().decode('utf-8', errors='replace').strip()
                    if line: # 応答があったらログに出す
                        print(f"Ack: {line}")
                    
                    if "executed" in line.lower():
                        return True
                time.sleep(0.01)
        
        except (DeviceTimeoutError, DeviceCommunicationError): # 自前の例外はそのまま再送出
            raise
        except Exception as e: # その他のシリアル通信エラー
            msg = f"Serial error on '{command.strip()}': {e}"
            print(f"Communication Error: {msg}")
            raise DeviceCommunicationError(msg)
        
        # ここに到達 = タイムアウト
        msg = f"No response for '{command.strip()}'."
        print(f"Timeout Error: {msg}")
        raise DeviceTimeoutError(msg)

    def send_heartbeat(self):
        """ ウォッチドッグタイマー用のハートビート送信 """
        if self.ser and self.ser.is_open:
            try:
                self.ser.write(b"HB\n")
            except:
                pass

    def read_line(self):
        """ 受信バッファから1行読み取る（MEASUREMENT_ENDなどの非同期イベント検知用） """
        if self.ser and self.ser.is_open and self.ser.in_waiting > 0:
            try:
                return self.ser.readline().decode('utf-8', errors='replace').strip()
            except:
                pass
        return None

    # --- 物理デバイスの操作メソッド ---

    def initialize_devices(self):
        """ 管理下の全デバイスを安全な初期状態（OFF/待機状態）にする """
        if not self.is_connected: return False

        print("Initializing devices... (Resetting all IO/Servo)")
        success = True

        # 1. 電極をすべてOFF (電極リレーは active-high: 0=OFF, 1=ON)
        for pin in self.config.electrode_map.values():
            try:
                self.send_command(f"DO,{pin},0\n")
                time.sleep(0.02)
            except (DeviceCommunicationError, DeviceTimeoutError) as e:
                print(f"Warning: Failed to initialize electrode pin {pin}: {e}")
                success = False
        
        # 2. サーボをすべてOFF角度へ
        for s in self.config.servo_map.values():
            if s.get('pin', -1) >= 0:
                try:
                    self.send_command(f"SV,{s['pin']},{s['off_angle']}\n")
                    time.sleep(0.05)
                except (DeviceCommunicationError, DeviceTimeoutError) as e:
                    print(f"Warning: Failed to initialize servo pin {s['pin']}: {e}")
                    success = False
        
        # 3. システムピン初期化 (DI1 と E-Stop は Active Low なので待機時は 1(HIGH))
        if self.config.di1_output_pin >= 0:
            try:
                self.send_command(f"DO,{self.config.di1_output_pin},1\n")
            except (DeviceCommunicationError, DeviceTimeoutError) as e:
                print(f"Warning: Failed to initialize DI1 pin: {e}")
                success = False
        
        time.sleep(0.05)
        
        if self.config.estop_pin >= 0:
            try:
                self.send_command(f"DO,{self.config.estop_pin},1\n")
            except (DeviceCommunicationError, DeviceTimeoutError) as e:
                print(f"Warning: Failed to initialize E-STOP pin: {e}")
                success = False

        if success:
            print("All physical devices initialized successfully.")
        else:
            print("Warning: Device initialization completed with some failures.")
        
        return success

    def set_digital(self, pin, value):
        """ 汎用デジタル出力 (電極は 0=OFF / 1=ON、システム信号は各ピンの仕様に従う) """
        if pin < 0: return False
        return self.send_command(f"DO,{pin},{value}\n")

    def set_servo(self, pin, angle):
        """ 汎用サーボ出力 (main.pyからガスラインを個別に操作する用) """
        if pin < 0: return False
        return self.send_command(f"SV,{pin},{angle}\n")
    
    def trigger_di1(self, pulse_duration=0.5):
        """ DI1 Outputピンにパルスを送る (手動トリガー用) """
        pin = self.config.di1_output_pin
        if pin < 0: return False
        
        # 例外はそのまま呼び出し元へ伝播させる
        self.send_command(f"DO,{pin},0\n") # LOW (ON)
        time.sleep(pulse_duration)
        self.send_command(f"DO,{pin},1\n") # HIGH (OFF)
        return True

    def start_measurement(self, pulse_duration=0.5):
        """ 測定開始トリガーを送る (DI1 Active Low パルス) """
        return self.trigger_di1(pulse_duration)

    def stop_measurement(self):
        """ 測定終了時に開始トリガーピンを待機状態(HIGH)へ戻す """
        pin = self.config.di1_output_pin
        if pin < 0:
            return False
        return self.send_command(f"DO,{pin},1\n")

    def trigger_estop(self, pulse_duration=0.5):
        """ 緊急停止トリガーを送る (E-STOP Active Low パルス) """
        pin = self.config.estop_pin
        if pin < 0: return False

        self.send_command(f"DO,{pin},0\n")
        time.sleep(pulse_duration)
        self.send_command(f"DO,{pin},1\n")
        return True

    def probe_communication(self):
        """ 通信健全性確認用の軽量プローブ（安全状態を維持するコマンド）"""
        # Active Lowピンは待機時HIGHが安全状態のため、HIGH再送でリンク確認する
        if self.config.estop_pin >= 0:
            return self.send_command(f"DO,{self.config.estop_pin},1\n")
        if self.config.di1_output_pin >= 0:
            return self.send_command(f"DO,{self.config.di1_output_pin},1\n")
        # プローブ対象ピンが無い場合は通信層としてはチェック不能なので成功扱い
        return True

    def set_estop(self, is_active):
        """ E-Stopの状態を設定する (True=停止/LOW, False=解除/HIGH) """
        pin = self.config.estop_pin
        if pin < 0: return False
        
        val = 0 if is_active else 1
        return self.send_command(f"DO,{pin},{val}\n")

    def set_interlock_enabled(self, enabled):
        """Firmware側の排他制御を有効/無効に切り替える。"""
        val = 1 if enabled else 0
        return self.send_command(f"IL,{val}\n")