#ifndef LIMIT_SWITCH_H
#define LIMIT_SWITCH_H

#include <Arduino.h>

// Active-HIGH limit switch: idle reads LOW, pressed reads HIGH.
class LimitSwitch {
public:
    LimitSwitch(uint8_t pin, uint16_t debounceMs = 20);

    void begin();

    // True when the switch has been stably pressed for at least debounceMs.
    bool pressed();

private:
    uint8_t pin;
    uint16_t debounceMs;
    bool lastRead;
    bool stableState;
    unsigned long lastChangeMs;
};

#endif
