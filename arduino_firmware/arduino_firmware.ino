#include <Servo.h>
#include "config.h"

// 定数定義 (とりあえずここにハードコードして動かす）
const int MAX_SERVOS = 12; 
const int MAX_DIGITAL_PINS = 60; 

// デジタルピン管理（使ったピンを記録）
int activeDigitalPins[MAX_DIGITAL_PINS];
int digitalPinCount = 0;

// サーボ管理
Servo servos[MAX_SERVOS];
int servoPins[MAX_SERVOS];
int servoCount = 0;
int servoOffAngles[MAX_SERVOS];

// 終了信号用（必要であれば使用）
const int DONE_PIN = 13;
int lastDoneState = HIGH;

void setup() {
  // config.h に BAUDRATE が定義されていればそれを使い、なければ9600
  #ifdef BAUDRATE
    Serial.begin(BAUDRATE);
  #else
    Serial.begin(9600);
  #endif

  pinMode(DONE_PIN, INPUT_PULLUP);

  // 管理配列の初期化
  for(int i=0; i<MAX_SERVOS; i++) { servoPins[i] = -1; servoOffAngles[i] = 0; }
  for(int i=0; i<MAX_DIGITAL_PINS; i++) { activeDigitalPins[i] = -1; }

  // Configからサーボのデフォルト角度を事前に読み込む
  #ifdef SERVO_COUNT_DEF
    for(int i=0; i<SERVO_COUNT_DEF; i++) {
      int pin = SERVO_DEFAULTS[i][0];
      int angle = SERVO_DEFAULTS[i][1];
      if(pin != -1) {
         int idx = getServoIndex(pin); 
         if(idx != -1) {
             servoOffAngles[idx] = angle;
         }
      }
    }
  #endif





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