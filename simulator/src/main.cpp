#include <WiFi.h>
#include <FirebaseESP32.h>
#include <DHT.h>
#include <ESP32Servo.h>

// ==========================================
// CẤU HÌNH WIFI VÀ FIREBASE (Thay thế config.h)
// ==========================================
#define WIFI_SSID "Wokwi-GUEST" 
#define WIFI_PASSWORD ""

#define DEVICE_ID "device_001"

// Database đã được kiểm chứng hoạt động (Không có https://)
#define FIREBASE_HOST "https://smartdrsoutheast1.firebasedatabase.app"
#define FIREBASE_AUTH "WUKYU6Cr479eWotma"
// ==========================================#

#define DHT_PIN        18
#define DHT_TYPE       DHT22
#define LIGHT_PIN      34
#define RAIN_PIN       16
#define MANUAL_PIN     26
#define LED_PIN        25
#define SERVO_PIN      2

// Các ngưỡng (Threshold)
#define LIGHT_THRESHOLD        1000 
#define HUMIDITY_MAX_THRESHOLD 80.0 
#define TEMP_MIN_THRESHOLD     22.0 

DHT dht(DHT_PIN, DHT_TYPE);
Servo servo1;

// --- KHAI BÁO THÊM CONFIG VÀ AUTH CHO FIREBASE ---
FirebaseData firebaseData;
FirebaseAuth auth;
FirebaseConfig config;
// -------------------------------------------------

bool isDrying = false;       
bool isManualMode = false;   
int previousButtonState = HIGH;
unsigned long lastButtonTime = 0;
unsigned long debounceDelay = 50;
bool isLongPressHandled = false;

unsigned long lastSendTime = 0;

void setup() {
  Serial.begin(115200);
  dht.begin();

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

  // 2. KHỞI TẠO FIREBASE MỚI
  config.host = FIREBASE_HOST;
  config.signer.tokens.legacy_token = FIREBASE_AUTH;
  
  // Tối ưu bộ nhớ SSL cho Wokwi
  firebaseData.setBSSLBufferSize(16384, 1024);
  
  Firebase.begin(&config, &auth); 
  Firebase.reconnectWiFi(true);
  
  // 3. Ghi Config ban đầu lên Firebase
  String configPath = "/Input_Config/" + String(DEVICE_ID);
  Firebase.setString(firebaseData, configPath + "/device_id", DEVICE_ID);
  Firebase.setString(firebaseData, configPath + "/mode", "auto");
  Firebase.setInt(firebaseData, configPath + "/updated_at", millis() / 1000);
}

void loop() {
  float temperature = dht.readTemperature();
  float humidity = dht.readHumidity();
  int lightLevel = analogRead(LIGHT_PIN);
  bool isRaining = (digitalRead(RAIN_PIN) == HIGH); 
  bool isDark = (lightLevel >= LIGHT_THRESHOLD); 
  bool isHighHumidity = (humidity >= HUMIDITY_MAX_THRESHOLD); 
  bool isLowTemp = (temperature <= TEMP_MIN_THRESHOLD);       

  int buttonState = digitalRead(MANUAL_PIN);

  if (buttonState == LOW && previousButtonState == HIGH) { 
    lastButtonTime = millis();
    isLongPressHandled = false;
  }

  if (buttonState == LOW && previousButtonState == LOW) {
    if (isManualMode && !isLongPressHandled && (millis() - lastButtonTime) > 2000) { 
      isManualMode = false;
      Serial.println("--- RETURNED TO AUTO MODE ---");
      lastButtonTime = millis(); 
      isLongPressHandled = true;
      Firebase.setString(firebaseData, "/Input_Config/" + String(DEVICE_ID) + "/mode", "auto");
    }
  }

  if (buttonState == HIGH && previousButtonState == LOW) {
    unsigned long pressDuration = millis() - lastButtonTime;
    if (pressDuration > debounceDelay && !isLongPressHandled) {
      isDrying = !isDrying; 
      isManualMode = true;  
      Serial.println("--- MANUAL OVERRIDE ACTIVATED ---");
      Firebase.setString(firebaseData, "/Input_Config/" + String(DEVICE_ID) + "/mode", "manual");
    }
  }
  previousButtonState = buttonState;

  digitalWrite(LED_PIN, isManualMode ? HIGH : LOW); 

  if (!isManualMode) {
    if (isRaining || isDark || isHighHumidity || isLowTemp) {
      isDrying = false; 
    } else {
      isDrying = true;  
    }
  }

  servo1.write(isDrying ? 90 : 0);

  Serial.printf("Temp: %.1fC | Hum: %.1f%% | Light: %d | Rain: %s | State: %s | Mode: %s\n",
                temperature, humidity, lightLevel, isRaining ? "YES" : "NO",
                isDrying ? "PHOI" : "THU", isManualMode ? "MANUAL" : "AUTOoo");

  // 4. Gửi Data lên Firebase mỗi 5 giây (Trong code đang để 2000ms = 2 giây)
  if (millis() - lastSendTime > 2000) {
    lastSendTime = millis();
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

  delay(2000); 
}