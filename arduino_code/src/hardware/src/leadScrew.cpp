#include "leadScrew.h"
#include <math.h>

LeadScrew::LeadScrew(StepperXYZ& stepper, float stepsPerMM,
    float maxTravel_mm, LimitSwitch& bottomLimit)
    : stepper_(stepper), bottomLimit(bottomLimit) {
    this->stepsPerMM = stepsPerMM;
    this->maxTravel_mm = maxTravel_mm;
    this->currentMm = 0.0f;
    this->stepResidual = 0.0f;
}
 
void LeadScrew::begin() {
    stepper_.begin();
    bottomLimit.begin();
}

void LeadScrew::moveBy_mm(float deltaMm) {
 
    float target = currentMm + deltaMm;
 
    if (target < 0.0f) {
        Serial.print("Z: target ");
        Serial.print(target);
        Serial.println(" below 0; move cancelled");
        return;
    }
    if (target > maxTravel_mm) {
        Serial.print("Z: target ");
        Serial.print(target);
        Serial.print(" exceeds max ");
        Serial.print(maxTravel_mm);
        Serial.println(" mm; move cancelled");
        return;
    }
 
    // Carry rounding leftover from previous move to avoid drift.
    float desiredSteps = deltaMm * stepsPerMM + stepResidual;
    long stepsToEmit = lroundf(desiredSteps);
 
    stepper_.step(stepsToEmit);
    stepResidual = desiredSteps - stepsToEmit;
    currentMm += deltaMm;
}
 
void LeadScrew::moveTo_mm(float mm) {
    moveBy_mm(mm - currentMm);
}

void LeadScrew::calibrate() {
    // If we're already on the switch, back off first so we always approach from above.
    if (bottomLimit.pressed()) {
        stepper_.setDirection(true);
        long backoffSteps = lroundf(stepsPerMM * 2.0f);
        for (long i = 0; i < backoffSteps && bottomLimit.pressed(); ++i) {
            stepper_.step();
        }
    }

    // Move down until the bottom limit switch is triggered, then back off slightly.
    stepper_.setDirection(false);
    while (!bottomLimit.pressed()) {
        stepper_.step();
    }
    stepper_.setDirection(true);
    long releaseSteps = lroundf(stepsPerMM * 1.0f);
    for (long i = 0; i < releaseSteps && bottomLimit.pressed(); ++i) {
        stepper_.step();
    }
    setZero();
}



