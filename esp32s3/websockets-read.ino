#include <WiFi.h>
#include <WebSocketsServer.h>

const char* ssid = "outeiroDev";
const char* password = "+Quixeras77";

const int relayPin = 14;


WebSocketsServer webSocket = WebSocketsServer(81);

const int analogPin = 1;

unsigned long lastSend = 0;
const int intervalMs = 200; // baja tasa de refresco (5 Hz)

void webSocketEvent(uint8_t num, WStype_t type, uint8_t * payload, size_t length) {
  switch(type) {
    case WStype_CONNECTED:
      Serial.println("Cliente conectado WebSocket");
      break;
    case WStype_DISCONNECTED:
      Serial.println("Cliente desconectado");
      break;
  }
  
}

void setup() {
  Serial.begin(115200);

  analogReadResolution(12);
  WiFi.begin(ssid, password);
  Serial.print("Conectando WiFi");

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nConectado");
  Serial.println(WiFi.localIP());

  webSocket.begin();
  webSocket.onEvent(webSocketEvent);
  digitalWrite(relayPin, LOW);

}

void loop() {
  webSocket.loop();

  if (millis() - lastSend > intervalMs) {
    lastSend = millis();

    int value = analogRead(analogPin);

    String msg = String(value);
    webSocket.broadcastTXT(msg);
  }
}
