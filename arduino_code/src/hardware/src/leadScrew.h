#ifndef LEAD_SCREW_H
#define LEAD_SCREW_H

#include "stepperXYZ.h"
#include "limitSwitch.h"
#include <Arduino.h>

class LeadScrew {
public:
    // lead_mm is the screw lead (mm of linear travel per motor revolution),
    // i.e. starts * pitch for a multi-start screw.
    LeadScrew(StepperXYZ& stepper,
              float stepsPerRev,
              int microstep,
              float lead_mm,
              float maxTravel_mm,
              LimitSwitch& bottomLimit);

    // Initializes the underlying stepper and bottom limit switch pins.
    void begin();

    void moveTo_mm(float mm);
    void moveBy_mm(float mm);
    void calibrate();
    float position_mm() const { return currentMm; }
    void setZero() { currentMm = 0.0f; }
    float stepsPerMm() const;

private:
    StepperXYZ& stepper_;
    LimitSwitch& bottomLimit;
    float stepsPerRev;
    int   microstep;
    float lead_mm;
    float maxTravel_mm;
    float currentMm;
};

#endif