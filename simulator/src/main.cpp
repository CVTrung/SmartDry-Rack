#include <WiFi.h>
#include <FirebaseESP32.h>
#include <DHT.h>
#include <ESP32Servo.h>
#include <LiquidCrystal_I2C.h>

// ==========================================
// CẤU HÌNH WIFI VÀ FIREBASE
// ==========================================
#define WIFI_SSID     "Wokwi-GUEST"
#define WIFI_PASSWORD ""

#define DEVICE_ID     "device_001"

#define FIREBASE_HOST ""
#define FIREBASE_AUTH ""
// ==========================================

#define DHT_PIN                18
#define DHT_TYPE               DHT22
#define LIGHT_PIN              34
#define RAIN_PIN               16
#define MANUAL_PIN             26
#define LED_PIN                25
#define SERVO_PIN              2

// Các ngưỡng (Threshold)
#define LIGHT_THRESHOLD        1000
#define HUMIDITY_MAX_THRESHOLD 80.0
#define TEMP_MIN_THRESHOLD     22.0

DHT dht(DHT_PIN, DHT_TYPE);
Servo servo1;
LiquidCrystal_I2C lcd(0x27, 16, 2);

// Khai báo Firebase Objects
FirebaseData firebaseData;
FirebaseAuth auth;
FirebaseConfig config;

// Trạng thái hệ thống
bool isDrying = false;       
bool isManualMode = false;   
int previousButtonState = HIGH;
unsigned long lastButtonTime = 0;
unsigned long debounceDelay = 10;
bool isLongPressHandled = false;

unsigned long lastSendTime = 0;
String previousRackState = ""; // Biến lưu trạng thái cũ để tránh ghi đè liên tục

void setup() {
  Serial.begin(115200);
  dht.begin();
  lcd.init();
  lcd.backlight();
  
  pinMode(RAIN_PIN, INPUT_PULLUP);
  pinMode(MANUAL_PIN, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);
  
  servo1.attach(SERVO_PIN);
  servo1.write(0);

  // 1. Kết nối WiFi
  Serial.print("Connecting to WiFi");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nConnected to WiFi!");

  // 2. Khởi tạo Firebase
  config.host = FIREBASE_HOST;
  config.signer.tokens.legacy_token = FIREBASE_AUTH;
  
  firebaseData.setBSSLBufferSize(16384, 1024);
  
  Firebase.begin(&config, &auth);
  Firebase.reconnectWiFi(true);
  
  // 3. Ghi Config ban đầu lên Firebase
  String configPath = "/Device_State/" + String(DEVICE_ID);
  Firebase.setString(firebaseData, configPath + "/device_id", DEVICE_ID);
  Firebase.setString(firebaseData, configPath + "/mode", "auto");
  Firebase.setInt(firebaseData, configPath + "/updated_at", millis() / 1000);
}

void loop() {
  // Đọc cảm biến
  float temperature = dht.readTemperature();
  float humidity = dht.readHumidity();
  int lightLevel = analogRead(LIGHT_PIN);
  bool isRaining = (digitalRead(RAIN_PIN) == HIGH);
  bool isDark = (lightLevel >= LIGHT_THRESHOLD);
  bool isHighHumidity = (humidity >= HUMIDITY_MAX_THRESHOLD);
  bool isLowTemp = (temperature <= TEMP_MIN_THRESHOLD);      

  int buttonState = digitalRead(MANUAL_PIN);

  // Xử lý nút nhấn chuyển Mode / Thủ công
  if (buttonState == LOW && previousButtonState == HIGH) {
    lastButtonTime = millis();
    isLongPressHandled = false;
  }

  if (buttonState == LOW && previousButtonState == LOW) {
    if (isManualMode && !isLongPressHandled && (millis() - lastButtonTime) > 2000) {
      isManualMode = false;
      Serial.println("--- RETURNED TO AUTO MODE ---");
      isLongPressHandled = true;
      Firebase.setString(firebaseData, "/Device_State/" + String(DEVICE_ID) + "/mode", "auto");
    }
  }

  if (buttonState == HIGH && previousButtonState == LOW) {
    unsigned long pressDuration = millis() - lastButtonTime;
    if (pressDuration > debounceDelay && !isLongPressHandled) {
      isDrying = !isDrying;
      isManualMode = true;  
      Serial.println("--- MANUAL OVERRIDE ACTIVATED ---");
        
      Firebase.setString(firebaseData, "/Device_State/" + String(DEVICE_ID) + "/mode", "manual");
      Firebase.setString(firebaseData, "/Device_State/" + String(DEVICE_ID) + "/rack_state", isDrying ? "extended" : "retracted");
    }
  }
  previousButtonState = buttonState;

  // Đèn LED báo hiệu chế độ Manual
  digitalWrite(LED_PIN, isManualMode ? HIGH : LOW);

  // Logic điều khiển Auto/Manual
  String currentRackState = isDrying ? "extended" : "retracted";

  if (!isManualMode) {
    // Chế độ Auto quyết định dựa vào cảm biến
    if (isRaining || isDark || isHighHumidity || isLowTemp) {
      isDrying = false;
    } else {
      isDrying = true;  
    }
    
    currentRackState = isDrying ? "extended" : "retracted";

    // Chỉ cập nhật lên Firebase khi trạng thái thay đổi để tránh ghi đè liên tục
    if (currentRackState != previousRackState) {
      Firebase.setString(firebaseData, "/Device_State/" + String(DEVICE_ID) + "/rack_state", currentRackState);
      previousRackState = currentRackState;
    }
  }

  // 4. Đồng bộ dữ liệu với Firebase mỗi 2 giây
  if (millis() - lastSendTime > 2000) {
    lastSendTime = millis();
    String statePath = "/Device_State/" + String(DEVICE_ID);
  
    // Đọc chế độ từ Web (Auto/Manual)
    if (Firebase.getString(firebaseData, statePath + "/mode")) {
      String webMode = firebaseData.stringData();
      isManualMode = (webMode == "manual");
    }

    // Nếu đang ở Manual, đồng bộ trạng thái phơi/thu từ Web xuống mạch
    if (isManualMode) {
      if (Firebase.getString(firebaseData, statePath + "/rack_state")) {
        String webState = firebaseData.stringData();
        isDrying = (webState == "extended");
      }
    }

    // Hiển thị LCD
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("Temp: " + String(temperature, 1) + "C");
    lcd.setCursor(0, 1);
    lcd.print(isManualMode ? "Mode: MANUAL" : "Status: AUTO");
    
    // Log Serial
    Serial.printf("Temp: %.1fC | Hum: %.1f%% | Light: %d | Rain: %s | State: %s | Mode: %s\n",
                  temperature, humidity, lightLevel, isRaining ? "YES" : "NO",
                  isDrying ? "PHOI" : "THU", isManualMode ? "MANUAL" : "AUTO");

    // Gửi thông số cảm biến lên Firebase
    String path = "/Input_Sensor/" + String(DEVICE_ID);
    Firebase.setString(firebaseData, path + "/device_id", DEVICE_ID);
    Firebase.setFloat(firebaseData, path + "/temperature_celsius", temperature);
    Firebase.setFloat(firebaseData, path + "/humidity_percent", humidity);
    Firebase.setFloat(firebaseData, path + "/light_lux", lightLevel);
    Firebase.setBool(firebaseData, path + "/rain_detected", isRaining);
    Firebase.setInt(firebaseData, path + "/timestamp", millis() / 1000);

    if (firebaseData.errorReason() != "") {
      Serial.println("Firebase Error: " + firebaseData.errorReason());
    } else {
      Serial.println(">>> Firebase Data Sent!");
    }
  }

  // Điều khiển Servo thực tế
  servo1.write(isDrying ? 90 : 0);
}