#ifndef LEAD_SCREW_H
#define LEAD_SCREW_H

#include "stepperXYZ.h"
#include "limitSwitch.h"
#include <Arduino.h>

class LeadScrew {
public:  
    LeadScrew(StepperXYZ& stepper,
              float stepsPerMM,
              float maxTravel_mm,
              LimitSwitch& bottomLimit);

    // Initializes the underlying stepper and bottom limit switch pins.
    void begin();

    void moveTo_mm(float mm);
    void moveBy_mm(float mm);
    void calibrate();
    float position_mm() const { return currentMm; }
    void setZero() { currentMm = 0.0f; stepResidual = 0.0f; }
 
private:
    StepperXYZ& stepper_;
    LimitSwitch& bottomLimit;
    float stepsPerMM;
    float maxTravel_mm;
    float currentMm;
    float stepResidual;
};

#endif