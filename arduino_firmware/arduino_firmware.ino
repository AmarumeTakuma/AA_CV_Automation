void setup() {
  // 通信を開始。環境に合わせてボーレートは変更する
  Serial.begin(9600);
}

// コマンドを実行
void loop() {
  // 受信バッファにデータがあるかチェック
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n'); // \nまでを1つのコマンドとして読み取る
    parseCommand(command);
  }
}

// コマンド解析
void parseCommand(String cmd) {
  cmd.trim(); // 空白を削除
  int commaIndex = cmd.indexOf(','); // カンマが何文字目にあるか

  // カンマが存在するかチェック
  if (commaIndex > 0) {
    String pinStr = cmd.substring(0, commaIndex); // カンマ前までを切り出す
    String valueStr = cmd.substring(commaIndex + 1); // カンマ後を切り出す
    
    // 整数に変換
    int pin = pinStr.toInt();
    int value = valueStr.toInt();
    
    pinMode(pin, OUTPUT);
    digitalWrite(pin, value);
    
    // ターミナルに返信
    Serial.print("Executed: Pin ");
    Serial.print(pin);
    Serial.print(", Value: ");
    Serial.println(value);

  // カンマが存在しない場合
  } else {
    Serial.println("Error: Invalid format. Expected 'pin,value'.");
  }
}