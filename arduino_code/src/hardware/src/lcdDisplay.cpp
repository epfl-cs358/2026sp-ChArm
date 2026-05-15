#include "lcdDisplay.h"
#include <string.h>

LCDDisplay::LCDDisplay(int rsPin, int ePin, int d4Pin, int d5Pin, int d6Pin, int d7Pin)
    : lcd(rsPin, ePin, d4Pin, d5Pin, d6Pin, d7Pin) {
    memset(lastLine1, 0, sizeof(lastLine1));
    memset(lastLine2, 0, sizeof(lastLine2));
    lastResyncMs = 0;
}

void LCDDisplay::begin() {
    lcd.begin(16, 2);
    lcd.clear();
    memset(lastLine1, 0, sizeof(lastLine1));
    memset(lastLine2, 0, sizeof(lastLine2));
    lastResyncMs = millis();
}

// Writes s into buf as exactly 16 chars (padded with spaces), null-terminated.
static void pad16(char buf[17], const String& s) {
    int len = (int)s.length();
    if (len > 16) len = 16;
    for (int i = 0; i < len; i++)      buf[i] = s[i];
    for (int i = len; i < 16; i++)     buf[i] = ' ';
    buf[16] = '\0';
}

void LCDDisplay::update(const String& line1, const String& line2) {
    char p1[17], p2[17];
    pad16(p1, line1);
    pad16(p2, line2);

    if (memcmp(p1, lastLine1, 16) != 0) {
        Serial.println(p1);
        lcd.setCursor(0, 0);
        lcd.print(p1);
        memcpy(lastLine1, p1, 17);
    }

    if (memcmp(p2, lastLine2, 16) != 0) {
        Serial.println(p2);
        lcd.setCursor(0, 1);
        lcd.print(p2);
        memcpy(lastLine2, p2, 17);
    }
}

void LCDDisplay::tick() {
    unsigned long now = millis();
    if (now - lastResyncMs < RESYNC_INTERVAL_MS) return;
    lastResyncMs = now;

    // Re-run the HD44780 init sequence to re-sync the 4-bit interface, then
    // redraw the current content. Recovers from a noise-induced nibble desync.
    lcd.begin(16, 2);
    lcd.setCursor(0, 0);
    lcd.print(lastLine1);
    lcd.setCursor(0, 1);
    lcd.print(lastLine2);
}

void LCDDisplay::clear() {
    lcd.clear();
    memset(lastLine1, 0, sizeof(lastLine1));
    memset(lastLine2, 0, sizeof(lastLine2));
}
