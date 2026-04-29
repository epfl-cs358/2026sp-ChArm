#include "scaraJoint.h"
#include <math.h>

ScaraJoint::ScaraJoint(StepperXYZ& stepper,
                       float stepsPerRev,
                       int microstep,
                       float gearRatio)
    : stepper_(stepper) {
    this->stepsPerRev = stepsPerRev;
    this->microstep = microstep;
    this->gearRatio = gearRatio;
    this->currentAngle = 0.0f;
    this->stepResidual = 0.0f;
    this->maxAngle = 360.0f;
}
 
float ScaraJoint::stepsPerDegree() const {
    // Uses stored microstep (not read from stepper) so it's always correct.
    return (stepsPerRev * microstep) / (gearRatio * 360.0f);
}
 
void ScaraJoint::moveBy(float deltaDeg) {
    float spd = stepsPerDegree();
    if (spd == 0.0f) return;

    float target = currentAngle + deltaDeg;

    /*
    if (target < 0.0f) {
        Serial.print("Joint: target ");
        Serial.print(target);
        Serial.println(" below 0; move cancelled");
        return;
    }
    if (target > maxAngle) {
        Serial.print("Joint: target ");
        Serial.print(target);
        Serial.print(" exceeds max ");
        Serial.print(maxAngle);
        Serial.println("; move cancelled");
        return;
    }
        */                 
 
    // Carry rounding leftover from previous move to avoid drift.
    float desiredSteps = deltaDeg * spd + stepResidual;
    long stepsToEmit = lroundf(desiredSteps);
 
    stepper_.step(stepsToEmit);
    stepResidual = desiredSteps - stepsToEmit;
    currentAngle += deltaDeg;
}
 
void ScaraJoint::moveTo(float angleDeg) {
    moveBy(angleDeg - currentAngle);
}
