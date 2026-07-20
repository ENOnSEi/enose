// ENose ESP32-S3 — MQTT node
//
// Reads the 4 TGS gas sensors and publishes readings to the broker, and
// receives base/medicion/cooldown/stop commands from the API. The payloads
// are identical to the legacy WebSocket firmware; only the transport changed.
//
//   publish  -> topic "enose/readings"
//               {"type":"reading","arduino_ms":N,"values":{"tgs2620":N,...}}
//   subscribe-> topic "enose/commands"
//               {"type":"command","estado":"base|medicion|cooldown"}
//               {"type":"command","action":"stop"}

#include <WiFi.h>
#include <PubSubClient.h>
#include "secrets.h"

const char* ssid = WIFI_SSID;
const char* password = WIFI_PASSWORD;

const char* mqttHost = MQTT_BROKER_HOST;
const int mqttPort = MQTT_BROKER_PORT;
const char* mqttUser = MQTT_USERNAME;
const char* mqttPass = MQTT_PASSWORD;

const char* TOPIC_READINGS = "enose/readings";
const char* TOPIC_COMMANDS = "enose/commands";

const int medicionRelayPin = 14;
const int idleRelayPin = 13;

// TODO: replace these placeholders with the real ESP32 ADC pins.
const int PIN_TGS2620 = 1;
const int PIN_TGS2611 = 2;
const int PIN_TGS2602 = 4;
const int PIN_TGS2600 = 5;

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

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

void handleCommand(const String& msg) {
  Serial.print("MQTT RX: ");
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

void onMqttMessage(char* topic, byte* payload, unsigned int length) {
  String msg;
  msg.reserve(length + 1);
  for (unsigned int i = 0; i < length; i++) {
    msg += (char)payload[i];
  }
  handleCommand(msg);
}

void connectWiFi() {
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
}

void connectMqtt() {
  while (!mqtt.connected()) {
    if (WiFi.status() != WL_CONNECTED) {
      connectWiFi();
    }

    String clientId = "enose-esp32-";
    clientId += String((uint32_t)ESP.getEfuseMac(), HEX);
    Serial.print("Conectando MQTT a ");
    Serial.print(mqttHost);
    Serial.print(":");
    Serial.println(mqttPort);

    bool ok;
    if (strlen(mqttUser) > 0) {
      ok = mqtt.connect(clientId.c_str(), mqttUser, mqttPass);
    } else {
      ok = mqtt.connect(clientId.c_str());
    }

    if (ok) {
      Serial.println("MQTT conectado");
      mqtt.subscribe(TOPIC_COMMANDS);
      Serial.print("Suscrito a ");
      Serial.println(TOPIC_COMMANDS);
    } else {
      Serial.print("Fallo MQTT, rc=");
      Serial.print(mqtt.state());
      Serial.println(" reintentando en 2s");
      delay(2000);
    }
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

  connectWiFi();

  mqtt.setServer(mqttHost, mqttPort);
  mqtt.setCallback(onMqttMessage);
  mqtt.setBufferSize(512);
}

void loop() {
  if (!mqtt.connected()) {
    connectMqtt();
  }
  mqtt.loop();

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

    mqtt.publish(TOPIC_READINGS, msg.c_str());
  }
}
