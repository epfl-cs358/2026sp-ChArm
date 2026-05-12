#include "limitAxis.h"
 
long findLimit(StepperXYZ& stepper, LimitSwitch& sw, bool direction, unsigned long debounceMs) {
    stepper.setDirection(direction);
    long steps = 0;
    while (true) {
        stepper.step();
        steps++;
        if (sw.pressed()) {
            delay(debounceMs);
            if (sw.pressed()) break;  // still pressed after wait = real contact
        }
    }
    return steps;
}

long backOff(StepperXYZ& stepper, LimitSwitch& sw, bool direction, unsigned long backOffDelayMs) {
    stepper.setDirection(direction);
    delay(50);
    long steps = 0;
    unsigned long stableStart = 0;
    bool timing = false;
    while (true) {
        stepper.step();
        steps++;
        if (sw.pressed()) {
            timing = false;  // still pressed, reset
        } else {
            if (!timing) { stableStart = millis(); timing = true; }
            if (millis() - stableStart >= backOffDelayMs) break;  // released for backOffDelayMs
        }
    }
    return steps;
}
 