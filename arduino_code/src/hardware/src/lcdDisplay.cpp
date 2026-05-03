#include "lcdDisplay.h"

LCDDisplay::LCDDisplay(int rsPin, int ePin, int d4Pin, int d5Pin, int d6Pin, int d7Pin)
    : lcd(rsPin, ePin, d4Pin, d5Pin, d6Pin, d7Pin) {
    this->lastLine1 = "";
    this->lastLine2 = "";
}

void LCDDisplay::begin() {
    lcd.begin(16, 2);
    lcd.clear();
    lastLine1 = "";
    lastLine2 = "";
}

static String pad16(const String &s) {
    String out = s;
    if (out.length() > 16) { out = out.substring(0, 16); }
    while (out.length() < 16) { out += ' '; }
    return out;
}

void LCDDisplay::update(String line1, String line2) {
    String p1 = pad16(line1);
    String p2 = pad16(line2);

    // Only rewrite lines that actually changed
    if (p1 != lastLine1) {
        lcd.setCursor(0, 0);
        lcd.print(p1);
        lastLine1 = p1;
    }

    if (p2 != lastLine2) {
        lcd.setCursor(0, 1);
        lcd.print(p2);
        lastLine2 = p2;
    }
}

void LCDDisplay::clear() {
    lcd.clear();
    lastLine1 = "";
    lastLine2 = "";
}
