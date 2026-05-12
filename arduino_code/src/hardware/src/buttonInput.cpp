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
}

void ButtonInput::begin() {
    pinMode(pinCLK, INPUT);
    pinMode(pinDT, INPUT);
    pinMode(pinSW, INPUT);
    lastCLKState = digitalRead(pinCLK);
    lastButtonState = digitalRead(pinSW);
}

InputEvent ButtonInput::readEvent() {
    // Check encoder rotation
    bool currentCLKState = digitalRead(pinCLK);
    if (currentCLKState != lastCLKState) {
        lastCLKState = currentCLKState;
        if (!currentCLKState) {  // Falling edge
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
    unsigned long now = millis();

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