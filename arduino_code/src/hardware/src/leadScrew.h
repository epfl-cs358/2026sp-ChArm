#ifndef LEAD_SCREW_H
#define LEAD_SCREW_H

#include "stepperXYZ.h"
#include <Arduino.h>

class LeadScrew {
public:
    LeadScrew(StepperXYZ& stepper, 
            uint8_t bottomLimitPin);

    void home(float backoff_mm = 1.0f);

    void moveTo_mm(float mm);
    void moveBy_mm(float mm);

    float position_mm() const;

private:
    StepperXYZ& stepper;
    uint8_t     bottomLimitPin;
    float       stepsPerMM;
    float       maxTravel_mm;

    bool bottomHit() const;
    bool wouldExceedTop(float mm) const;
};

#endif