#ifndef LEAD_SCREW_H
#define LEAD_SCREW_H

#include "stepperXYZ.h"
#include <Arduino.h>

class LeadScrew {
public:
    LeadScrew(StepperXYZ& stepper, 
            uint8_t bottomLimitPin,
            float StepsPerMM,
            float maxTravel_mm,
            float gripperLength);

    void home(float backoff_mm = 1.0f);

    void moveTo_mm(float mm);
    void moveBy_mm(float mm);

    float position_mm() const;

private:
    StepperXYZ& stepper;
    uint8_t     bottomLimitPin;
    float       stepsPerMM;
    float maxTravel_mm;
    float gripperLength;

    bool bottomHit() const;
    bool wouldExceedTop(float mm) const;
};

#endif