#include "leadScrew.h"
#include <math.h>

LeadScrew::LeadScrew(StepperXYZ& stepper,
                     float stepsPerRev,
                     int microstep,
                     float lead_mm,
                     float maxTravel_mm,
                     LimitSwitch& bottomLimit)
    : stepper_(stepper), bottomLimit(bottomLimit) {
    this->stepsPerRev = stepsPerRev;
    this->microstep = microstep;
    this->lead_mm = lead_mm;
    this->maxTravel_mm = maxTravel_mm;
    this->currentMm = 0.0f;
}

void LeadScrew::begin() {
    stepper_.begin();
    bottomLimit.begin();
}

float LeadScrew::stepsPerMm() const {
    // Uses stored microstep (not read from stepper) so it's always correct.
    return (stepsPerRev * microstep) / lead_mm;
}

void LeadScrew::moveBy_mm(float deltaMm) {
    float spm = stepsPerMm();
    if (spm == 0.0f) return;

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

    long stepsToEmit = lroundf(deltaMm * spm);
    stepper_.step(stepsToEmit);
    // Physical (emitted) position, not the commanded one — see ScaraJoint.
    currentMm += (float)stepsToEmit / spm;
}
 
void LeadScrew::moveTo_mm(float mm) {
    moveBy_mm(mm - currentMm);
}

void LeadScrew::calibrate() {
    // Move down until the bottom limit switch is triggered, then set that position to zero.
    stepper_.setDirection(false); 
    while (!bottomLimit.pressed()) {
        stepper_.step();
    }
    stepper_.setDirection(true);
    moveBy_mm(5.0f); // back off a bit to avoid wearing out the switch
    setZero();
}



