#ifndef LIMIT_AXIS_H
#define LIMIT_AXIS_H
 
#include "stepperXYZ.h"
#include "limitSwitch.h"
#include <Arduino.h>
 
// Drives a stepper in the given direction until the switch triggers
long findLimit(StepperXYZ& stepper, LimitSwitch& sw, bool direction, unsigned long backOffDelayMs);

// Backs off from a triggered switch until it releases
long backOff(StepperXYZ& stepper, LimitSwitch& sw, bool direction, unsigned long backOffDelayMs);
 
#endif
 