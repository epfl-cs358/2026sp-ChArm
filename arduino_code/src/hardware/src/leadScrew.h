#ifndef LEAD_SCREW_H
#define LEAD_SCREW_H

#include "stepperXYZ.h"
#include <Arduino.h>

class LeadScrew {
public:
    LeadScrew(StepperXYZ& stepper, 
            uint8_t bottomLimitPin);

    // Home the Z-axis by driving down until the bottom limit switch fires,
    // then backing off by backoff_mm so the switch is not held pressed.
    void home(float backoff_mm = 1.0f);

    void moveTo_mm(float mm);
    void moveBy_mm(float mm);

    float position_mm() const;

    // Returns true after a successful home() sequence.
    bool isHomed() const { return homed; }

private:
    StepperXYZ& stepper;
    uint8_t     bottomLimitPin;
    float       stepsPerMM;
    float       maxTravel_mm;
    bool        homed;

    bool bottomHit() const;
    bool wouldExceedTop(float mm) const;
};

#endif
