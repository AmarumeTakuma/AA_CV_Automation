import serial
import time

class ArduinoDevice:
    def __init__(self, config):
        self.config = config  # ConfigManagerのインスタンス
        self.ser = None
        self.is_connected = False
        self.is_measuring = False

    def connect(self):
        try:
            self.ser = serial.Serial(self.config.serial_port, self.config.baudrate, timeout=1)
            time.sleep(2)
            self.is_connected = True
            return True
        except serial.SerialException as e:
            print(f"Connection Error: {e}")
            return False

    def close(self):
        if self.ser and self.ser.is_open:
            self.initialize_devices() # 安全のため閉じる前に初期化
            self.ser.close()
        self.is_connected = False

    def send_command(self, command):
        if not (self.ser and self.ser.is_open):
            return False
        
        try:        
            self.ser.reset_input_buffer()
            self.ser.write(command.encode())
            print(f"Sent: {command.strip()}")

            # 簡易ハンドシェイク（タイムアウト付き）
            start_time = time.time()
            while (time.time() - start_time) < 1.0:
                if self.ser.in_waiting > 0:
                    line = self.ser.readline().decode('utf-8', errors='replace').strip()
                    if "executed" in line.lower():
                        return True
                time.sleep(0.01)

            print(f"Timeout: {command.strip()}")
            return False
        
        except Exception as e:
            print(f"Comm Error: {e}")
            return False

    def send_heartbeat(self):
        if self.ser and self.ser.is_open:
            try:
                self.ser.write(b"HB\n")
            except: pass

    # 受信データの読み取り（MEASUREMENT_ENDなどの検知用）
    def read_line(self):
        if self.ser and self.ser.is_open and self.ser.in_waiting > 0:
            try:
                return self.ser.readline().decode('utf-8', errors='replace').strip()
            except:
                pass
        return None

    # --- 操作メソッド ---

    def initialize_devices(self):
        if not self.is_connected: return False

        # 電極OFF
        for pin in self.config.electrode_map.values():
            self.send_command(f"DO,{pin},0\n")
            time.sleep(0.02)
        
        # サーボOFF
        for s in self.config.servo_map.values():
            if s['pin'] >= 0:
                self.send_command(f"SV,{s['pin']},{s['off_angle']}\n")
                time.sleep(0.05)
        
        # システムピン初期化
        if self.config.start_pin >= 0:
            self.send_command(f"DO,{self.config.start_pin},1\n")
        time.sleep(0.05)
        if self.config.estop_pin >= 0:
            self.send_command(f"DO,{self.config.estop_pin},1\n")

        print("All devices initialized.")
        return True

    def set_digital(self, pin, value):
        if pin < 0: return
        self.send_command(f"DO,{pin},{value}\n")

    def set_servo(self, pin, angle):
        if pin < 0: return
        self.send_command(f"SV,{pin},{angle}\n")

    def start_measurement(self):
        if self.config.start_pin < 0: return False
        
        if self.send_command(f"DO,{self.config.start_pin},0\n"):
            self.is_measuring = True
            return True
        return False

    def stop_measurement(self):
        self.is_measuring = False
        if self.config.start_pin >= 0:
            self.send_command(f"DO,{self.config.start_pin},1\n")

    def trigger_estop(self):
        if self.config.estop_pin < 0: return
        
        self.send_command(f"DO,{self.config.estop_pin},0\n")
        time.sleep(0.5)
        self.send_command(f"DO,{self.config.estop_pin},1\n")
        self.stop_measurement()