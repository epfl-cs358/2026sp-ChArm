#include "limitSwitch.h"
 
LimitSwitch::LimitSwitch(uint8_t pin, bool activeLow)
    : pin(pin), activeLow(activeLow) {}
 
void LimitSwitch::begin() {
    pinMode(pin, activeLow ? INPUT_PULLUP : INPUT);
}
 
bool LimitSwitch::isTriggered() const {
    return activeLow ? (digitalRead(pin) == LOW)
                     : (digitalRead(pin) == HIGH);
}