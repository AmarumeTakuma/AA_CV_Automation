import serial
import serial.tools.list_ports
import time

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
            print(f"Connection Error: {e}")
            return False

    def close(self):
        """ 通信を安全に閉じる """
        if self.ser and self.ser.is_open:
            self.initialize_devices()  # 安全のため、ポートを閉じる前に全ピンを初期化
            self.ser.close()
        self.is_connected = False

    def send_command(self, command):
        """ コマンドを送信し、'executed' の応答(Ack)を待つ """
        if not (self.ser and self.ser.is_open):
            print(f"Communication Error: Command '{command.strip()}' skipped (Not Connected)")
            return False
        
        try:        
            self.ser.reset_input_buffer()
            self.ser.write(command.encode())
            print(f"Sent: {command.strip()}")

            # 簡易ハンドシェイク（タイムアウト1.0秒）
            start_time = time.time()
            while (time.time() - start_time) < 1.0:
                if self.ser.in_waiting > 0:
                    line = self.ser.readline().decode('utf-8', errors='replace').strip()
                    if line:
                        # 応答があったらログに出す
                        print(f"Ack: {line}") 
                    
                    if "executed" in line.lower():
                        return True
                time.sleep(0.01)

            print(f"Parameters Error: Timeout - No response for '{command.strip()}'")
            return False
        
        except Exception as e:
            print(f"Communication Error: {e}")
            return False

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

        # 1. 電極をすべてOFF (0)
        for pin in self.config.electrode_map.values():
            self.send_command(f"DO,{pin},0\n")
            time.sleep(0.02)
        
        # 2. サーボをすべてOFF角度へ
        for s in self.config.servo_map.values():
            if s.get('pin', -1) >= 0:
                self.send_command(f"SV,{s['pin']},{s['off_angle']}\n")
                time.sleep(0.05)
        
        # 3. システムピン初期化 (DI1 と E-Stop は Active Low なので待機時は 1(HIGH))
        if self.config.di1_output_pin >= 0:
            self.send_command(f"DO,{self.config.di1_output_pin},1\n")
        time.sleep(0.05)
        
        if self.config.estop_pin >= 0:
            self.send_command(f"DO,{self.config.estop_pin},1\n")

        print("All physical devices initialized.")
        return True

    def set_digital(self, pin, value):
        """ 汎用デジタル出力 (main.pyから電極などを個別に操作する用) """
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
        
        if self.send_command(f"DO,{pin},0\n"): # LOW (ON)
            time.sleep(pulse_duration)
            self.send_command(f"DO,{pin},1\n") # HIGH (OFF)
            return True
        return False

    def set_estop(self, is_active):
        """ E-Stopの状態を設定する (True=停止/LOW, False=解除/HIGH) """
        pin = self.config.estop_pin
        if pin < 0: return False
        
        val = 0 if is_active else 1
        return self.send_command(f"DO,{pin},{val}\n")