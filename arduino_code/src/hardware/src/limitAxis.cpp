#include "limitAxis.h"
 
long findLimit(StepperXYZ& stepper, LimitSwitch& sw, bool direction) {
    stepper.setDirection(direction);
    long steps = 0;
    while (sw.isNotTriggered()) { stepper.step(); steps++; }
    return steps;
}

long backOff(StepperXYZ& stepper, LimitSwitch& sw, bool direction) {
    stepper.setDirection(direction);
    long steps = 0;
    while (!sw.isNotTriggered()) { stepper.step(); steps++; }
    stepper.step();
    return steps;
}
 