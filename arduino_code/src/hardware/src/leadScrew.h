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
              float gripperLength = 0.0f);
 
    void moveTo_mm(float mm);
    void moveBy_mm(float mm);
 
    float position_mm() const { return currentMm; }
    void setZero() { currentMm = 0.0f; stepResidual = 0.0f; }
 
private:
    StepperXYZ& stepper_;
    float stepsPerMM;
    float maxTravel_mm;
    float gripperLength;
    float currentMm;
    float stepResidual;
};

#endif