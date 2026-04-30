#include "limitAxis.h"
 
long findLimit(StepperXYZ& stepper, LimitSwitch& sw, bool direction) {
    stepper.setDirection(direction);
    long steps = 0;
    while (sw.isNotTriggered()) { stepper.step(); steps++; }
    return steps;
}

long backOff(StepperXYZ& stepper, LimitSwitch& sw, bool direction) {
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
            if (millis() - stableStart >= 200) break;  // stable for 200ms
        }
    }
    return steps;
}
 