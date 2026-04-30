#include "limitAxis.h"
 
long findLimit(StepperXYZ& stepper, LimitSwitch& sw, bool direction, unsigned long debounceMs) {
    stepper.setDirection(direction);
    long steps = 0;
    while (true) {
        stepper.step();
        steps++;
        if (!sw.isNotTriggered()) {
            delay(debounceMs);
            if (!sw.isNotTriggered()) break;  // still triggered after wait = real contact
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
        if (!sw.isNotTriggered()) {
            timing = false;  // bounced back, reset
        } else {
            if (!timing) { stableStart = millis(); timing = true; }
            if (millis() - stableStart >= backOffDelayMs) break;  // stable for backOffDelayMs
        }
    }
    return steps;
}
 