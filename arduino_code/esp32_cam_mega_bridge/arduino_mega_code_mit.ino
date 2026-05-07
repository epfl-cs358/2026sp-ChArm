// =========================
// Arduino Mega <-> ESP32-CAM Serial Test
//
// Mega Serial1 pins:
// TX1 = pin 18
// RX1 = pin 19
// =========================

#define ESP32_BAUD 9600

void setup() {
  Serial.begin(115200);      // USB serial to computer
  Serial1.begin(ESP32_BAUD); // Serial1 to ESP32-CAM

  delay(1000);

  Serial.println();
  Serial.println("================================");
  Serial.println("Arduino Mega ready");
  Serial.println("================================");
  Serial.println("Commands:");
  Serial.println("  s = send STATUS to ESP32-CAM");
  Serial.println("  c = send CAPTURE to ESP32-CAM");
  Serial.println("  i = ask ESP32-CAM for IP");
  Serial.println();
}

void loop() {
  if (Serial.available()) {
    char ch = Serial.read();

    if (ch == 's' || ch == 'S') {
      Serial.println("[MEGA] Sending STATUS to ESP32-CAM...");
      Serial1.println("STATUS");
    }

    else if (ch == 'c' || ch == 'C') {
      Serial.println("[MEGA] Sending CAPTURE to ESP32-CAM...");
      Serial1.println("CAPTURE");
    }

    else if (ch == 'i' || ch == 'I') {
      Serial.println("[MEGA] Asking ESP32-CAM for IP...");
      Serial1.println("IP");
    }
  }

  if (Serial1.available()) {
    String msg = Serial1.readStringUntil('\n');
    msg.trim();

    if (msg.length() > 0) {
      Serial.print("[MEGA] ESP32-CAM says: ");
      Serial.println(msg);
    }
  }
}
