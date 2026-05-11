#include "limitSwitch.h"

LimitSwitch::LimitSwitch(uint8_t pin, uint16_t debounceMs)
        : pin(pin),
          debounceMs(debounceMs),
          lastRead(false),
          stableState(false),
          lastChangeMs(0) {}

void LimitSwitch::begin() {
    pinMode(pin, INPUT);
    stableState = (digitalRead(pin) == HIGH);
    lastRead = stableState;
    lastChangeMs = millis();
}

bool LimitSwitch::pressed() {
    bool current = (digitalRead(pin) == HIGH);
    if (current != lastRead) {
        lastRead = current;
        lastChangeMs = millis();
    }
    if (millis() - lastChangeMs >= debounceMs) {
        stableState = lastRead;
    }
    return stableState;
}
