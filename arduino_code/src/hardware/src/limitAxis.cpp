#include "limitAxis.h"
 
void findLimit(StepperXYZ& stepper, LimitSwitch& sw, bool direction) {
    stepper.setDirection(direction);
    while (!sw.isTriggered()) { stepper.step(); }
}
 