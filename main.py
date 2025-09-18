import serial, time

# ピンの対応表
# 接続を変更した場合はここを変更
# 0番と1番ピンは通信用に使われるので使用不可
# 'エイリアス': 実際のピン番号
PIN_MAP = {
    'sw1': 2,
    'sw2': 4,
    'sw3': 10,
}

def main():
    print("Commands: '<alias> <value>' or '<alias>, <value>', e.g., 'sw1 1' or 'exit'")
    print("Available aliases:", list(PIN_MAP.keys()))
    
    # Arduinoと接続
    try:
        # 環境に合わせてCOMポートとボーレートを変更
        ser = serial.Serial("COM5", 9600, timeout = 1)
        time.sleep(2)

    # ポートが異なったり他のプログラムが使用中のときエラー
    except serial.SerialException as e:
        print(f"Error opening port: {e}")
        return

    # PIN_MAPにある全てのピンに対してOFF(0)コマンドを送信
    print("\nInitializing all pins to LOW...")
    for alias, pin_number in PIN_MAP.items():
        command_to_send = f"{pin_number},0\n"
        ser.write(command_to_send.encode())
        print(f"  > Initializing {alias} (pin {pin_number}) to LOW")
        time.sleep(0.1)
    print("Initialization complete.\n")

    # ループとユーザー入力
    try:
        while True:
            # ユーザー入力を小文字にして空白削除
            user_input = input("\n> ").lower().strip()
            
            # 終了
            if user_input == 'exit':
                break

            # コマンドを分割
            if ',' in user_input:
                parts = user_input.split(',') # カンマで分割
            else:
                parts = user_input.split() # スペースで分割
            
            # 正しいフォーマットでなければエラー
            if len(parts) != 2:
                print("  Error: Invalid format. Use '<alias> <value>'.")
                continue

            alias = parts[0].strip()
            value_str = parts[1].strip()

            # エイリアスが対応表に存在するかチェック
            if alias in PIN_MAP:
                # エイリアスから実際のピン番号を取得
                pin_number = PIN_MAP[alias]
                
                # 値が数字かチェック
                if value_str.isdigit():
                    value = int(value_str)

                    # 値が0, 1以外のときエラー
                    if value not in [0, 1]:
                        print("  Error: Value must be 0 or 1.")
                        continue
                    
                    # Arduinoに送るコマンドを作成
                    command_to_send = f"{pin_number},{value}\n"
                    
                    print(f"  Translating '{alias}' to pin {pin_number}...")
                    
                    # Arduinoにバイト列として送信して返信を受け取る
                    ser.write(command_to_send.encode())
                    print(f"  Sent to Arduino ->: {command_to_send.strip()}")
                    time.sleep(0.1)
                    if ser.in_waiting > 0: # 受信バッファにデータがあるかチェック
                        response = ser.readline().decode().strip()
                        print(f"  Recv from Arduino <-: {response}")

                # 値が数字でない場合        
                else:
                    print("  Error: Value must be a number.")

            # 対応表にないエイリアスが入力された場合
            else:
                print(f"  Error: Alias '{alias}' not found.")

    # Ctrl+Cによる終了
    except KeyboardInterrupt:
        print("\nExiting...")

    # ポート開放
    finally:
        ser.close()
        print("Port closed.")

if __name__ == '__main__':
    main()