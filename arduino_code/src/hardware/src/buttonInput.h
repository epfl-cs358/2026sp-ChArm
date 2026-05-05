#ifndef BUTTON_INPUT_H
#define BUTTON_INPUT_H

#include <Arduino.h>

enum InputEvent {
    INPUT_NONE,
    INPUT_NEXT,        // Encoder clockwise
    INPUT_PREV,        // Encoder counterclockwise
    INPUT_SELECT       // Short press
};

class ButtonInput {
public:
    ButtonInput(int clkPin, int dtPin, int swPin);

    void begin();

    // Call frequently in loop(); returns one event at a time
    InputEvent readEvent();

private:
    int pinCLK;
    int pinDT;
    int pinSW;

    bool lastCLKState;
    bool lastButtonState;
    unsigned long buttonPressStartMs;

    unsigned long debounceMs;
    unsigned long lastButtonChangeMs;
};

#endif