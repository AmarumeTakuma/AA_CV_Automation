#include <Servo.h>

// 定数定義 (Pythonと合わせる)
// ボーレート
const int BAUDRATE = 9600;
// ピン番号
const int PINS_ELECTRODE[] = {2, 4, 7, 8, 10, 12}; // Python: in ELECTRODE_MAP
const int PIN_SERVO_A = 3;  // Python: 'Gas Line A'
const int PIN_SERVO_B = 5;  // Python: 'Gas Line B'
const int PIN_SERVO_PURGE = 6;  // Python: 'Gas Purge'
const int PIN_START = 11; // Python: START_PIN
const int PIN_E_STOP = 13; // Python: E_STOP_PIN
// サーボの初期位置
const int SERVO_OFF_ANGLE = 0;

// 電極数の計算
int electrodeCount = sizeof(PINS_ELECTRODE) / sizeof(PINS_ELECTRODE[0]);

// Servoオブジェクト
Servo servoA;  // Gas Line A用
Servo servoB;  // Gas Line B用
Servo servoPurge; // Gas Purge用

void setup() {
  Serial.begin(BAUDRATE);

  // 電極の初期化
  for (int i = 0; i < electrodeCount; i++) {
    pinMode(PINS_ELECTRODE[i], OUTPUT);
    digitalWrite(PINS_ELECTRODE[i], LOW);
  }
  
  // サーボの初期化
  servoA.attach(PIN_SERVO_A);
  servoB.attach(PIN_SERVO_B);
  servoPurge.attach(PIN_SERVO_PURGE);
  
  // サーボを初期位置(OFF)へ
  servoA.write(SERVO_OFF_ANGLE);
  servoB.write(SERVO_OFF_ANGLE);
  servoPurge.write(SERVO_OFF_ANGLE);
  
  // 測定開始/エマストピン: Active Lowなので、初期値はHIGH(OFF)にしておく
  pinMode(PIN_START, OUTPUT);
  digitalWrite(PIN_START, HIGH); // 待機状態
  
  pinMode(PIN_E_STOP, OUTPUT);
  digitalWrite(PIN_E_STOP, HIGH); // 待機状態

  Serial.println("Arduino Ready.");
}

void loop() {
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    parseCommand(command);
  }
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
      
      // 安全のため角度を0-180に制限
      angle = constrain(angle, 0, 180); 
      
      // ピン番号に応じて正しいサーボを動かす
      if (pin == PIN_SERVO_A) servoA.write(angle);
      else if (pin == PIN_SERVO_B) servoB.write(angle);
      else if (pin == PIN_SERVO_PURGE) servoPurge.write(angle);
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