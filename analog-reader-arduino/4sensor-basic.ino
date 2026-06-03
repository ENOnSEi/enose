const int tgs2620 = A3;
const int tgs2611 = A2;
const int tgs2602 = A1;
const int tgs2600 = A0;

void setup() {
  Serial.begin(9600);
}

void loop() {
  unsigned long t = millis();

  int v20 = analogRead(tgs2620);
  int v11 = analogRead(tgs2611);
  int v02 = analogRead(tgs2602);
  int v00 = analogRead(tgs2600);

  Serial.print(t);
  Serial.print(",");

  Serial.print(v20);
  Serial.print(",");
  Serial.print(v11);
  Serial.print(",");
  Serial.print(v02);
  Serial.print(",");
  Serial.println(v00);

  delay(250);
}
