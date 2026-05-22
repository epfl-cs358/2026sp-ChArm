#include "buttonInput.h"

ButtonInput::ButtonInput(int pinCLK, int pinDT, int pinSW) {
    this->pinCLK = pinCLK;
    this->pinDT = pinDT;
    this->pinSW = pinSW;
    this->lastCLKState = HIGH;
    this->lastButtonState = HIGH;
    this->buttonPressStartMs = 0;
    this->debounceMs = 20;
    this->lastButtonChangeMs = 0;
    this->lastEncoderMs = 0;
}

void ButtonInput::begin() {
    // INPUT_PULLUP gives the encoder/button pins a defined HIGH idle level so
    // floating lines and electrical noise can't register as spurious events.
    pinMode(pinCLK, INPUT_PULLUP);
    pinMode(pinDT, INPUT_PULLUP);
    pinMode(pinSW, INPUT_PULLUP);
    lastCLKState = digitalRead(pinCLK);
    lastButtonState = digitalRead(pinSW);
}

InputEvent ButtonInput::readEvent() {
    // Check encoder rotation with debounce
    unsigned long now = millis();
    bool currentCLKState = digitalRead(pinCLK);
    if (currentCLKState != lastCLKState) {
        lastCLKState = currentCLKState;
        if (!currentCLKState && (now - lastEncoderMs >= 50)) {  // Falling edge + debounce
            lastEncoderMs = now;
            bool dtState = digitalRead(pinDT);
            if (dtState != currentCLKState) {
                return INPUT_NEXT;  // Clockwise
            } else {
                return INPUT_PREV;  // Counterclockwise
            }
        }
    }

    // Check button
    bool currentButtonState = digitalRead(pinSW);

    if (currentButtonState != lastButtonState) {
        lastButtonChangeMs = now;
        lastButtonState = currentButtonState;

        if (currentButtonState == LOW) {  // Press
            buttonPressStartMs = now;
        } else {  // Release
            unsigned long pressDuration = now - buttonPressStartMs;
            if (pressDuration >= debounceMs) {
                return INPUT_SELECT;
            }
        }
    }

    return INPUT_NONE;
}