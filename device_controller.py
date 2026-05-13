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
            available_ports = [p.device for p in serial.tools.list_ports.comports()]
            is_available = self.config.serial_port in available_ports
            return is_available, available_ports
        except Exception as e:
            print(f"Port check skipped due to error: {e}")
            return True, []

    def connect(self):
        """ Arduinoとのシリアル通信を開始する """
        try:
            self.ser = serial.Serial(self.config.serial_port, self.config.baudrate, timeout=1)
            time.sleep(2)  # Arduinoの自動リセット完了を待つ
            self.is_connected = True
            return True
        except PermissionError as e:
            msg = (
                f"Could not open {self.config.serial_port}: {e}. "
                "The port is likely already in use by Arduino Serial Monitor or another app."
            )
            print(f"Connection Error: {msg}")
            raise DeviceCommunicationError(msg)
        except serial.SerialException as e:
            msg = f"Could not open {self.config.serial_port}: {e}"
            print(f"Connection Error: {msg}")
            raise DeviceCommunicationError(msg)

    def close(self):
        """ 通信を安全に閉じる """
        if self.ser and self.ser.is_open:
            try:
                self.initialize_devices()
            except Exception as e:
                print(f"Warning: Device initialization during close failed: {e}")
            self.ser.close()
        self.is_connected = False

    def send_command(self, command):
        """ コマンドを送信し、応答を待つ """
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
            # prepare command base (e.g. "GPIO,SET") for matching echoed responses
            cmd_parts = command.strip().split(',')
            cmd_base = ','.join(cmd_parts[:2]) if len(cmd_parts) >= 2 else cmd_parts[0]
            while (time.time() - start_time) < timeout:
                if self.ser.in_waiting > 0:
                    line = self.ser.readline().decode('utf-8', errors='replace').strip()
                    if line:
                        print(f"Ack: {line}")
                    # 新コマンド体系では "ACK" 系の応答を確認
                    # Accept explicit ACK/OK responses
                    if "ACK" in line or any(x in line for x in ["executed", "OK", "EMERGENCY_STOP", "INIT_OK", "HB"]):
                        return True
                    # Also accept the device echoing the executed command (e.g. "GPIO,SET,12,1")
                    if command.strip() in line:
                        return True
                    # Accept matched command base (e.g. "GPIO,SET") — but treat explicit device errors as failures
                    if cmd_base in line:
                        if "Error" in line or line.startswith("Error:"):
                            msg = f"Device reported error on '{command.strip()}': {line}"
                            print(f"Communication Error: {msg}")
                            raise DeviceCommunicationError(msg)
                        return True
                    # Or accept common device-prefixed responses
                    if line.startswith(("GPIO,", "PCA,", "SERVO,", "SYS,", "SYSTEM,")):
                        return True
                time.sleep(0.01)
        
        except (DeviceTimeoutError, DeviceCommunicationError):
            raise
        except Exception as e:
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
                self.ser.write(b"SYS,HB\n")
            except:
                pass

    def read_line(self):
        """ 受信バッファから1行読み取る """
        if self.ser and self.ser.is_open and self.ser.in_waiting > 0:
            try:
                return self.ser.readline().decode('utf-8', errors='replace').strip()
            except:
                pass
        return None

    # --- 物理デバイスの操作メソッド ---

    def initialize_devices(self):
        """ 管理下の全デバイスを安全な初期状態にする """
        if not self.is_connected:
            return False

        print("Initializing devices... (SYS,INIT)")
        success = True

        try:
            self.send_command("SYS,INIT\n")
            time.sleep(0.1)
        except (DeviceCommunicationError, DeviceTimeoutError) as e:
            print(f"Warning: Device initialization failed: {e}")
            success = False

        if success:
            print("All physical devices initialized successfully.")
        else:
            print("Warning: Device initialization completed with some failures.")
        
        return success

    def set_gpio(self, pin, value):
        """ GPIO ピン制御 (DI1, E-STOP など) """
        if pin < 0:
            return False
        return self.send_command(f"GPIO,SET,{pin},{value},\n")

    def pulse_gpio(self, pin, duration_ms):
        """ GPIO ピンにパルスを送る """
        if pin < 0:
            return False
        return self.send_command(f"GPIO,PULSE,{pin},{duration_ms},\n")

    def set_pca_relay(self, channel, value):
        """ PCA9685 経由のリレー制御 """
        if channel < 0:
            return False
        return self.send_command(f"PCA,SET,{channel},{value},\n")

    def set_servo(self, channel, angle):
        """ PCA9685 経由のサーボ制御 """
        if channel < 0:
            return False
        return self.send_command(f"SERVO,SET,{channel},{angle},\n")
    
    def trigger_di1(self, pulse_duration=0.5):
        """ DI1 Outputピンにパルスを送る (手動トリガー用) """
        pin = self.config.di1_output_pin
        if pin < 0:
            return False
        
        pulse_ms = int(pulse_duration * 1000)
        return self.pulse_gpio(pin, pulse_ms)

    def start_measurement(self, pulse_duration=0.5):
        """ 測定開始トリガーを送る (DI1 パルス) """
        return self.trigger_di1(pulse_duration)

    def stop_measurement(self):
        """ 測定終了時に開始トリガーピンを待機状態へ戻す """
        pin = self.config.di1_output_pin
        if pin < 0:
            return False
        return self.set_gpio(pin, 1)  # HIGH (OFF, Active Low)

    def trigger_estop(self, pulse_duration=0.5):
        """ 緊急停止トリガーを送る (E-STOP パルス) """
        pin = self.config.estop_pin
        if pin < 0:
            return False

        pulse_ms = int(pulse_duration * 1000)
        return self.pulse_gpio(pin, pulse_ms)

    def probe_communication(self):
        """ 通信健全性確認用プローブ """
        if self.config.estop_pin >= 0:
            return self.set_gpio(self.config.estop_pin, 1)  # HIGH (OFF, Active Low)
        if self.config.di1_output_pin >= 0:
            return self.set_gpio(self.config.di1_output_pin, 1)  # HIGH (OFF, Active Low)
        return True

    def set_estop(self, is_active):
        """ E-Stopの状態を設定する (True=停止/LOW, False=解除/HIGH) """
        pin = self.config.estop_pin
        if pin < 0:
            return False
        
        val = 0 if is_active else 1  # Active Low
        return self.set_gpio(pin, val)

    def set_interlock_enabled(self, enabled):
        """排他制御の有効/無効を切り替える"""
        val = 1 if enabled else 0
        return self.send_command(f"SYS,IL,{val}\n")
