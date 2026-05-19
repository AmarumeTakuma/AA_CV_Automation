#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>
#include "config.h"

// PCA9685 初期化 (I2C address 0x40)
Adafruit_PWMServoDriver pca9685(0x40);

// GPIO ピン管理
int activeGPIOPins[MAX_GPIO_PINS];
int gpioPinCount = 0;

// 終了信号用
int lastDoneState = HIGH;
int lastDo1State = HIGH;
int lastDo2State = HIGH;
int lastHwErrState = LOW;

// ウォッチドッグ用
unsigned long lastHeartbeatTime = 0;
bool watchdogActive = false;
bool interlockEnabled = true;

// PCA9685 制御用定数
const uint16_t SERVO_MIN_US = 900;
const uint16_t SERVO_MAX_US = 2100;
const uint8_t PCA_FREQ_HZ = 50;
const uint16_t PWM_FULL_ON = 4095;
const uint16_t PWM_FULL_OFF = 0;

void setup() {
  // 通信設定
  #ifdef BAUDRATE
    Serial.begin(BAUDRATE);
  #else
    Serial.begin(9600);
  #endif

  delay(500);

  // I2C 初期化 (PCA9685 通信用)
  Wire.begin();

  // オンボードLEDを出力に設定し、OFFにしておく
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);

  Serial.println("[BOOT] Starting initialization...");

  // GPIO ピン初期化 (測定終了信号)
  if (DONE_PIN >= 0) {
    pinMode(DONE_PIN, INPUT_PULLUP);
  }

  if (DO1_PIN >= 0) {
    pinMode(DO1_PIN, INPUT_PULLUP);
  }
  if (DO2_PIN >= 0) {
    pinMode(DO2_PIN, INPUT_PULLUP);
  }
  if (HW_ERR_PIN >= 0) {
    pinMode(HW_ERR_PIN, INPUT);
  }

  // GPIO システム制御ピン初期化
  if (DI1_OUTPUT_PIN >= 0) {
    digitalWrite(DI1_OUTPUT_PIN, HIGH);
    pinMode(DI1_OUTPUT_PIN, OUTPUT);
  }
  if (ESTOP_PIN >= 0) {
    digitalWrite(ESTOP_PIN, HIGH);
    pinMode(ESTOP_PIN, OUTPUT);
  }

  Serial.println("[BOOT] GPIO initialized.");

  // PCA9685 初期化
  Serial.println("[BOOT] Initializing PCA9685...");
  if (!pca9685.begin()) {
    Serial.println("ERROR: PCA9685 not found!");
    digitalWrite(LED_BUILTIN, HIGH); // エラー表示
  } else {
    pca9685.setOscillatorFrequency(27000000);
    pca9685.setPWMFreq(PCA_FREQ_HZ);
    // すべてのリレーとサーボを安全初期化
    initializeAllPCA();
    Serial.println("PCA9685 initialized.");
  }

  // GPIO 管理配列初期化
  for(int i = 0; i < MAX_GPIO_PINS; i++) {
    activeGPIOPins[i] = -1;
  }

  Serial.println("Arduino Ready. Command format: SYS,HB / GPIO,SET,pin,val / PCA,SET,ch,val / SERVO,SET,ch,angle");
}

void loop() {
  // コマンド受信
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    parseCommand(command);
  }

  // ウォッチドッグ監視
  if (watchdogActive) {
    if (millis() - lastHeartbeatTime > WATCHDOG_TIMEOUT) {
      forceStopAll();
      watchdogActive = false;
    }
  }

  // 測定終了信号の監視
  if (DONE_PIN >= 0) {
    int currentDoneState = digitalRead(DONE_PIN);
    if (lastDoneState == HIGH && currentDoneState == LOW) {
      Serial.println("MEASUREMENT_END");
      delay(50);
    }
    lastDoneState = currentDoneState;
  }

  // DO1 (測定終了フラグとして扱う)
  if (DO1_PIN >= 0) {
    int currentDo1 = digitalRead(DO1_PIN);
    if (lastDo1State == HIGH && currentDo1 == LOW) {
      Serial.println("MEASUREMENT_END");
      delay(20);
    }
    lastDo1State = currentDo1;
  }

  // DO2 (下地: 変化検出を通知)
  if (DO2_PIN >= 0) {
    int currentDo2 = digitalRead(DO2_PIN);
    if (currentDo2 != lastDo2State) {
      Serial.print("DO2,EVENT,");
      Serial.println(currentDo2);
      lastDo2State = currentDo2;
    }
  }

  // HW Error 出力の監視 (Hz-Proが200ms間 HIGH を出す)
  if (HW_ERR_PIN >= 0) {
    int currentHw = digitalRead(HW_ERR_PIN);
    if (currentHw != lastHwErrState) {
      // 立ち上がり/立ち下がりを通知
      Serial.print("HW_ERR,");
      Serial.println(currentHw == HIGH ? "1" : "0");
      lastHwErrState = currentHw;
    }
  }
}

// ============================================
// PCA9685 ユーティリティ
// ============================================

uint16_t angleToPWM(uint8_t angle) {
  angle = constrain(angle, 0, 180);
  const uint32_t periodUs = 1000000UL / PCA_FREQ_HZ;
  const uint16_t pulseUs = map(angle, 0, 180, SERVO_MIN_US, SERVO_MAX_US);
  return (uint16_t)((pulseUs * 4096UL) / periodUs);
}

void setPCARelay(uint8_t channel, bool on) {
  const uint16_t valueOn = PWM_FULL_ON;
  const uint16_t valueOff = PWM_FULL_OFF;
  pca9685.setPWM(channel, 0, on ? valueOn : valueOff);
}

void setPCAServo(uint8_t channel, uint8_t angle) {
  uint16_t pwmValue = angleToPWM(angle);
  pca9685.setPWM(channel, 0, pwmValue);
}

void initializeAllPCA() {
  // すべてのリレーをOFF
  for (uint8_t i = 0; i < 16; i++) {
    pca9685.setPWM(i, 0, PWM_FULL_OFF);
  }
}

// ============================================
// GPIO 制御
// ============================================

void setGPIO(int pin, int value) {
  if (pin < 0) return;

  // ホワイトリスト確認
  bool valid = false;
  for (int i = 0; i < VALID_GPIO_COUNT; i++) {
    if (VALID_GPIO_PINS[i] == pin) {
      valid = true;
      break;
    }
  }
  if (!valid) {
    Serial.print("Error: GPIO pin ");
    Serial.print(pin);
    Serial.println(" is not whitelisted.");
    return;
  }

  pinMode(pin, OUTPUT);
  digitalWrite(pin, value);

  // アクティブリストに登録
  bool found = false;
  for (int i = 0; i < gpioPinCount; i++) {
    if (activeGPIOPins[i] == pin) {
      found = true;
      break;
    }
  }
  if (!found && gpioPinCount < MAX_GPIO_PINS) {
    activeGPIOPins[gpioPinCount] = pin;
    gpioPinCount++;
  }

  Serial.print("GPIO,SET,");
  Serial.print(pin);
  Serial.print(",");
  Serial.println(value);
}

void pulseGPIO(int pin, unsigned int durationMs) {
  if (pin < 0) return;

  setGPIO(pin, 0); // LOW (ON)
  delay(durationMs);
  setGPIO(pin, 1); // HIGH (OFF)

  Serial.print("GPIO,PULSE,");
  Serial.print(pin);
  Serial.print(",");
  Serial.println(durationMs);
}

// ============================================
// PCA 制御
// ============================================

void setPCA(uint8_t channel, int value) {
  if (channel >= 16) {
    Serial.println("Error: PCA channel out of range (0-15).");
    return;
  }

  setPCARelay(channel, value != 0);

  Serial.print("PCA,SET,");
  Serial.print(channel);
  Serial.print(",");
  Serial.println(value);
}

// ============================================
// サーボ制御 (PCA9685 経由)
// ============================================

void setServo(uint8_t channel, uint8_t angle) {
  if (channel >= 16) {
    Serial.println("Error: Servo channel out of range (0-15).");
    return;
  }

  angle = constrain(angle, 0, 180);
  setPCAServo(channel, angle);

  Serial.print("SERVO,SET,");
  Serial.print(channel);
  Serial.print(",");
  Serial.println(angle);
}

// ============================================
// 緊急停止 & 初期化
// ============================================

void forceStopAll() {
  // GPIO をすべて安全側へ
  if (DI1_OUTPUT_PIN >= 0) {
    digitalWrite(DI1_OUTPUT_PIN, HIGH);
  }
  if (ESTOP_PIN >= 0) {
    digitalWrite(ESTOP_PIN, HIGH);
  }

  // PCA9685 をすべてOFFへ
  initializeAllPCA();

  // GPIO リストをリセット
  gpioPinCount = 0;
  for (int i = 0; i < MAX_GPIO_PINS; i++) {
    activeGPIOPins[i] = -1;
  }

  // 警告LED点灯
  digitalWrite(LED_BUILTIN, HIGH);

  Serial.println("SYSTEM,EMERGENCY_STOP");
}

void initializeDevices() {
  // GPIO 初期化
  if (DI1_OUTPUT_PIN >= 0) {
    setGPIO(DI1_OUTPUT_PIN, 1); // HIGH (OFF, Active Low)
  }
  if (ESTOP_PIN >= 0) {
    setGPIO(ESTOP_PIN, 1); // HIGH (OFF, Active Low)
  }

  // PCA9685 初期化
  initializeAllPCA();

  // 排他制御の有効化
  interlockEnabled = true;

  Serial.println("SYSTEM,INIT_OK");
}

// ============================================
// コマンド解析
// ============================================

void parseCommand(String cmd) {
  cmd.trim();

  if (cmd.length() == 0) return;

  // コマンド分割
  int firstComma = cmd.indexOf(',');
  if (firstComma == -1) {
    Serial.println("Error: Invalid command format.");
    return;
  }

  String cmdType = cmd.substring(0, firstComma);

  // ============ SYS コマンド ============
  if (cmdType == "SYS") {
    int nextComma = cmd.indexOf(',', firstComma + 1);
    String subCmd = (nextComma == -1) 
      ? cmd.substring(firstComma + 1) 
      : cmd.substring(firstComma + 1, nextComma);

    if (subCmd == "HB") {
      lastHeartbeatTime = millis();
      watchdogActive = true;
      digitalWrite(LED_BUILTIN, LOW);
      Serial.println("SYS,HB,ACK");
    } 
    else if (subCmd == "IL") {
      if (nextComma != -1) {
        int val = cmd.substring(nextComma + 1).toInt();
        interlockEnabled = (val != 0);
        Serial.print("SYS,IL,");
        Serial.println(interlockEnabled ? "ON" : "OFF");
      } else {
        Serial.println("Error: IL format (expected SYS,IL,0/1).");
      }
    }
    else if (subCmd == "INIT") {
      initializeDevices();
    }
    else if (subCmd == "STOP") {
      forceStopAll();
    }
    else {
      Serial.println("Error: Unknown SYS subcommand.");
    }
  }

  // ============ GPIO コマンド ============
  else if (cmdType == "GPIO") {
    // GPIO,SET,pin,value
    // GPIO,PULSE,pin,duration_ms
    int comma1 = cmd.indexOf(',', firstComma + 1);
    if (comma1 == -1) {
      Serial.println("Error: GPIO format invalid.");
      return;
    }

    String action = cmd.substring(firstComma + 1, comma1);
    int comma2 = cmd.indexOf(',', comma1 + 1);
    if (comma2 == -1) {
      Serial.println("Error: GPIO format invalid.");
      return;
    }

    int pin = cmd.substring(comma1 + 1, comma2).toInt();

    if (action == "SET") {
      int comma3 = cmd.indexOf(',', comma2 + 1);
      int value = 0;
      if (comma3 == -1) {
        // allow value without an extra comma (tolerant parsing)
        value = cmd.substring(comma2 + 1).toInt();
      } else {
        value = cmd.substring(comma2 + 1, comma3).toInt();
      }
      setGPIO(pin, value);
    } 
    else if (action == "PULSE") {
      unsigned int duration = cmd.substring(comma2 + 1).toInt();
      pulseGPIO(pin, duration);
    }
    else {
      Serial.println("Error: Unknown GPIO action.");
    }
  }

  // ============ PCA コマンド ============
  else if (cmdType == "PCA") {
    // PCA,SET,channel,value
    int comma1 = cmd.indexOf(',', firstComma + 1);
    if (comma1 == -1) {
      Serial.println("Error: PCA format invalid.");
      return;
    }

    String action = cmd.substring(firstComma + 1, comma1);
    int comma2 = cmd.indexOf(',', comma1 + 1);
    if (comma2 == -1) {
      Serial.println("Error: PCA format invalid.");
      return;
    }

    uint8_t channel = cmd.substring(comma1 + 1, comma2).toInt();

    if (action == "SET") {
      int comma3 = cmd.indexOf(',', comma2 + 1);
      int value = 0;
      if (comma3 == -1) {
        value = cmd.substring(comma2 + 1).toInt();
      } else {
        value = cmd.substring(comma2 + 1, comma3).toInt();
      }
      setPCA(channel, value);
    }
    else {
      Serial.println("Error: Unknown PCA action.");
    }
  }

  // ============ SERVO コマンド ============
  else if (cmdType == "SERVO") {
    // SERVO,SET,channel,angle
    int comma1 = cmd.indexOf(',', firstComma + 1);
    if (comma1 == -1) {
      Serial.println("Error: SERVO format invalid.");
      return;
    }

    String action = cmd.substring(firstComma + 1, comma1);
    int comma2 = cmd.indexOf(',', comma1 + 1);
    if (comma2 == -1) {
      Serial.println("Error: SERVO format invalid.");
      return;
    }

    uint8_t channel = cmd.substring(comma1 + 1, comma2).toInt();

    if (action == "SET") {
      int comma3 = cmd.indexOf(',', comma2 + 1);
      uint8_t angle = 0;
      if (comma3 == -1) {
        angle = cmd.substring(comma2 + 1).toInt();
      } else {
        angle = cmd.substring(comma2 + 1, comma3).toInt();
      }
      setServo(channel, angle);
    }
    else {
      Serial.println("Error: Unknown SERVO action.");
    }
  }

  else {
    Serial.println("Error: Unknown command type.");
  }
}