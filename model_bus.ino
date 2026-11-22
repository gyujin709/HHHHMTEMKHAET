#include <WiFi.h>
#include <HTTPClient.h>

constexpr char WIFI_NAME[] = "WiFi SSID";
constexpr char WIFI_PASSWORD[] = "WiFi password";
constexpr char SERVER_URL[] = "http://192.168.0.10:8765/api/share";
constexpr char MODEL_KEY[] = "Server key";
constexpr char ROUTE[] = "51";  // 51, 6719, 220, G1124
constexpr int SENSOR_PIN = 4;
constexpr int ACTIVE = LOW;    // Button to GND or HW-870 DO (3.3 V).
constexpr bool TIMED_DEMO = false;
constexpr unsigned LONGEST_STEP = 8; // 0→1→2→3→4→3→2→1→0

unsigned step = 0;
bool raw = false, detected = false, armed = false, dirty = true;
uint32_t changedAt = 0, lastAdvance = 0, lastSend = 0;

void setup() {
  Serial.begin(115200);
  pinMode(SENSOR_PIN, INPUT_PULLUP);
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_NAME, WIFI_PASSWORD);
}

void loop() {
  const uint32_t now = millis();
  const bool active = digitalRead(SENSOR_PIN) == ACTIVE;
  if (active != raw) {
    raw = active;
    changedAt = now;
  }
  if (!raw && now - changedAt >= 150) {
    armed = true;
    detected = false;
  }
  bool advance = false;
  if (raw && now - changedAt >= 30 && !detected && armed) {
    detected = true;
    armed = false;
    advance = !TIMED_DEMO;
  }
  if (TIMED_DEMO && now - lastAdvance >= 5000) advance = true;
  if (advance) {
    step = (step + 1) % LONGEST_STEP;
    lastAdvance = now;
    dirty = true;
  }
  if (WiFi.status() != WL_CONNECTED || now - lastSend < (dirty ? 250u : 2000u)) return;
  lastSend = now;
  WiFiClient client;
  HTTPClient http;
  if (!http.begin(client, SERVER_URL)) return;
  http.setConnectTimeout(400);
  http.setTimeout(600);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Model-Key", MODEL_KEY);
  // Keep BusLive relay's /api/share and me.line, with a model stop index.
  const String body = String("{\"me\":{\"line\":\"") + ROUTE + "\",\"step\":" + step + "}}";
  const int status = http.POST(body);
  http.end();
  dirty = status != 200;
  Serial.printf("step=%u HTTP=%d\n", step, status);
}
