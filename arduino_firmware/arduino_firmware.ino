#include <Servo.h>

// ボーレート
const int BAUDRATE = 9600;

// --- ピン番号定義 ---
// Cell A
const int CELL_A_WE_PIN = 2;
const int CELL_A_CE_PIN = 3;
const int CELL_A_RE_PIN = 4;
// Cell B
const int CELL_B_WE_PIN = 8;
const int CELL_B_CE_PIN = 9;
const int CELL_B_RE_PIN = 10;

// まとめて初期化するための配列
const int ALL_ELECTRODE_PINS[] = {
  CELL_A_WE_PIN, CELL_A_CE_PIN, CELL_A_RE_PIN,
  CELL_B_WE_PIN, CELL_B_CE_PIN, CELL_B_RE_PIN
};
const int ELECTRODE_COUNT = sizeof(ALL_ELECTRODE_PINS) / sizeof(ALL_ELECTRODE_PINS[0]);

// --- 排他制御 (インターロック) 設定 ---
// ※現在は定義のみ。Arduino側で強制チェックしたい場合はロジック追加が必要
const int EXCLUSIVE_PAIRS[][2] = {
  {CELL_A_WE_PIN, CELL_B_WE_PIN}, // WE同士
  {CELL_A_CE_PIN, CELL_B_CE_PIN}, // CE同士
  {CELL_A_RE_PIN, CELL_B_RE_PIN}  // RE同士
};
const int PAIR_COUNT = sizeof(EXCLUSIVE_PAIRS) / sizeof(EXCLUSIVE_PAIRS[0]);

// Gas Line
const int SERVO_A_PIN = 5;      // Python: 'Gas Line A'
const int SERVO_B_PIN = 6;      // Python: 'Gas Line B'
const int SERVO_PURGE_PIN = 7;  // Python: 'Gas Purge'

// HZ-Pro
const int START_PIN = 11; // Python: START_PIN
const int E_STOP_PIN = 12; // Python: E_STOP_PIN
const int DONE_PIN = 13; // Python: STOP_PIN (Input)

// サーボの初期位置
const int SERVO_OFF_ANGLE = 0;

// Servoインスタンス
Servo servoA;      // Gas Line A用
Servo servoB;      // Gas Line B用
Servo servoPurge;  // Gas Purge用

int lastDoneState = HIGH; // 信号状態記憶用変数

void setup() {
  Serial.begin(BAUDRATE);

  // 電極の初期化
  for (int i = 0; i < ELECTRODE_COUNT; i++) {
    pinMode(ALL_ELECTRODE_PINS[i], OUTPUT);
    digitalWrite(ALL_ELECTRODE_PINS[i], LOW);
  }
  
  // サーボの初期化
  servoA.attach(SERVO_A_PIN);
  servoB.attach(SERVO_B_PIN);
  servoPurge.attach(SERVO_PURGE_PIN);
  
  // サーボを初期位置(OFF)へ
  servoA.write(SERVO_OFF_ANGLE);
  servoB.write(SERVO_OFF_ANGLE);
  servoPurge.write(SERVO_OFF_ANGLE);
  
  // 測定開始/エマストピン: Active Lowなので、初期値はHIGH(OFF)にしておく
  pinMode(START_PIN, OUTPUT);
  digitalWrite(START_PIN, HIGH);
  
  pinMode(E_STOP_PIN, OUTPUT);
  digitalWrite(E_STOP_PIN, HIGH);

  pinMode(DONE_PIN, INPUT_PULLUP);

  Serial.println("Arduino Ready.");
}

void loop() {
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    parseCommand(command);
  }

  // 測定終了信号の監視処理 (Active Low: HIGH -> LOW)
  int currentDoneState = digitalRead(DONE_PIN);
  if (lastDoneState == HIGH && currentDoneState == LOW) {
      Serial.println("MEASUREMENT_END");
      delay(50); // チャタリング防止
  }
  lastDoneState = currentDoneState;
}

// コマンド解析
void parseCommand(String cmd) {
  cmd.trim(); // 前後の空白を削除
  
  if (cmd.startsWith("DO,")) { 
    // DigitalOutput用コマンド (DO,ピン番号,0/1)
    int firstComma = cmd.indexOf(',');
    int secondComma = cmd.indexOf(',', firstComma + 1);
    
    if (firstComma > 0 && secondComma > 0) {
       int pin = cmd.substring(firstComma + 1, secondComma).toInt(); // ピン番号
       int value = cmd.substring(secondComma + 1).toInt();           // 値 (0 or 1)
       
       pinMode(pin, OUTPUT); 
       digitalWrite(pin, value);
       
       Serial.print("Executed DigitalOutput. Pin: "); Serial.print(pin);
       Serial.print(", Val: "); Serial.println(value);
    } else { 
      Serial.println("Error: DO format (expected DO,pin,val)."); 
    }

  } else if (cmd.startsWith("SV,")) { 
    // サーボ制御コマンド (SV,ピン番号,角度)
    int firstComma = cmd.indexOf(',');
    int secondComma = cmd.indexOf(',', firstComma + 1);
    
    if (firstComma > 0 && secondComma > 0) {
      int pin = cmd.substring(firstComma + 1, secondComma).toInt(); // ピン番号
      int angle = cmd.substring(secondComma + 1).toInt();           // 角度
      
      // 安全のためこちら側でも角度を0-180に制限
      angle = constrain(angle, 0, 180); 
      
      // ピン番号に応じて正しいサーボを動かす
      if (pin == SERVO_A_PIN) servoA.write(angle);
      else if (pin == SERVO_B_PIN) servoB.write(angle);
      else if (pin == SERVO_PURGE_PIN) servoPurge.write(angle);
      else {
        Serial.println("Error: Unknown servo pin.");
        return; 
      }
      
      Serial.print("Executed Servo. Pin: "); Serial.print(pin);
      Serial.print(", Angle: "); Serial.println(angle);
      
    } else { 
      Serial.println("Error: SV format (expected SV,pin,angle)."); 
    }
    
  } else {
    // どちらのヘッダーでもない場合
    if (cmd.length() > 0) {
        Serial.println("Error: Unknown command prefix.");
    }
  }
}