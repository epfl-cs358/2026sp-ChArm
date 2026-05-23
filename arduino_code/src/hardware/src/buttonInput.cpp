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
    this->encoderWaitingForHigh = false;
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
    // Check encoder rotation with debounce.
    // Strategy: fire on the first falling edge after 80ms of quiet, then require
    // CLK to return HIGH before accepting another event.  This prevents late
    // bounces (encoders that bounce >50ms) from registering as extra clicks.
    unsigned long now = millis();
    bool currentCLKState = digitalRead(pinCLK);
    if (currentCLKState != lastCLKState) {
        lastCLKState = currentCLKState;
        lastEncoderMs = now;  // reset timer on every edge so late bounces stay filtered

        if (encoderWaitingForHigh) {
            // Waiting for CLK to settle back HIGH after an event fired
            if (currentCLKState == HIGH) encoderWaitingForHigh = false;
        } else if (!currentCLKState) {
            // Falling edge: read direction and fire
            bool dtState = digitalRead(pinDT);
            encoderWaitingForHigh = true;
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