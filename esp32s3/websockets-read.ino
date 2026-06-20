#include <WiFi.h>
#include <WebSocketsServer.h>

const char* ssid = "DIGIFIBRA-stQx";
const char* password = "PsYcFK7c5NfQ";

const int medicionRelayPin = 14;
const int idleRelayPin = 13;

WebSocketsServer webSocket = WebSocketsServer(81);

// TODO: replace these placeholders with the real ESP32 ADC pins.
const int PIN_TGS2620 = 1;
const int PIN_TGS2611 = 2;
const int PIN_TGS2602 = 4;
const int PIN_TGS2600 = 5;

String currentEstado = "base";

unsigned long lastSend = 0;
const int intervalMs = 200; // baja tasa de refresco (5 Hz)

void applyEstado(const String& estado) {
  currentEstado = estado;

  if (estado == "medicion") {
    digitalWrite(medicionRelayPin, HIGH);
    digitalWrite(idleRelayPin, LOW);
  } else {
    digitalWrite(medicionRelayPin, LOW);
    digitalWrite(idleRelayPin, HIGH);
  }

  Serial.print("Estado recibido: ");
  Serial.println(currentEstado);
}

void handleCommand(uint8_t * payload, size_t length) {
  String msg;
  msg.reserve(length + 1);
  for (size_t i = 0; i < length; i++) {
    msg += (char)payload[i];
  }

  Serial.print("WebSocket RX: ");
  Serial.println(msg);

  if (msg.indexOf("\"action\"") >= 0 && msg.indexOf("\"stop\"") >= 0) {
    applyEstado("stop");
    return;
  }

  if (msg.indexOf("\"estado\"") < 0) {
    return;
  }

  if (msg.indexOf("\"base\"") >= 0) {
    applyEstado("base");
  } else if (msg.indexOf("\"medicion\"") >= 0) {
    applyEstado("medicion");
  } else if (msg.indexOf("\"cooldown\"") >= 0) {
    applyEstado("cooldown");
  }
}

void webSocketEvent(uint8_t num, WStype_t type, uint8_t * payload, size_t length) {
  switch(type) {
    case WStype_CONNECTED:
      Serial.println("Cliente conectado WebSocket");
      break;
    case WStype_DISCONNECTED:
      Serial.println("Cliente desconectado");
      break;
    case WStype_TEXT:
      handleCommand(payload, length);
      break;
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println();
  Serial.println("Arrancando ESP32...");

  analogReadResolution(12);
  pinMode(medicionRelayPin, OUTPUT);
  pinMode(idleRelayPin, OUTPUT);
  digitalWrite(medicionRelayPin, LOW);
  digitalWrite(idleRelayPin, HIGH);
  Serial.println("Pines configurados");

  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  Serial.print("Conectando WiFi");

  unsigned long wifiStart = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - wifiStart < 20000) {
    delay(500);
    Serial.print(".");
  }

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println();
    Serial.println("No se pudo conectar al WiFi");
    return;
  }

  Serial.println("\nConectado");
  Serial.println(WiFi.localIP());

  webSocket.begin();
  webSocket.onEvent(webSocketEvent);
  Serial.println("WebSocket iniciado en puerto 81");
}

void loop() {
  webSocket.loop();

  if (millis() - lastSend > intervalMs) {
    lastSend = millis();

    String msg = "{";
    msg += "\"type\":\"reading\",";
    msg += "\"arduino_ms\":" + String(millis()) + ",";
    msg += "\"values\":{";
    msg += "\"tgs2620\":" + String(analogRead(PIN_TGS2620)) + ",";
    msg += "\"tgs2611\":" + String(analogRead(PIN_TGS2611)) + ",";
    msg += "\"tgs2602\":" + String(analogRead(PIN_TGS2602)) + ",";
    msg += "\"tgs2600\":" + String(analogRead(PIN_TGS2600));
    msg += "}}";

    webSocket.broadcastTXT(msg);
  }
}
