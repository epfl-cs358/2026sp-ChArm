#ifndef LIMIT_AXIS_H
#define LIMIT_AXIS_H
 
#include "stepperXYZ.h"
#include "limitSwitch.h"
#include <Arduino.h>
 
// Drives a stepper in the given direction until the switch triggers.
void findLimit(StepperXYZ& stepper, LimitSwitch& sw, bool direction);
 
#endif
 