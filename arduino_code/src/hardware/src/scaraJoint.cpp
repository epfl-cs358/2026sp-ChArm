#include "scaraJoint.h"
#include <math.h>

/*ScaraJoint::ScaraJoint(StepperXYZ& stepper, LimitSwitch& minSwitch, LimitSwitch& maxSwitch, 
                        float stepsPerRev, float gearRatio)
    : stepper(stepper), minSwitch(minSwitch), maxSwitch(maxSwitch) {
    this->stepsPerRev = stepsPerRev;
    this->gearRatio = gearRatio;
    this->max_Angle = 0.0f;
    this->min_Angle = 0.0f;
}
    */

ScaraJoint::ScaraJoint(StepperXYZ& stepper,
                       float stepsPerRev,
                       int microstep,
                       float gearRatio)
    : stepper(stepper) {
    this->stepsPerRev = stepsPerRev;
    this->microstep = microstep;
    this->gearRatio = gearRatio;
    this->currentAngle = 0.0f;
    this->stepResidual = 0.0f;
}
 
float ScaraJoint::stepsPerDegree() const {
    // Uses stored microstep (not read from stepper) so it's always correct.
    return (stepsPerRev * microstep * gearRatio) / 360.0f;
}
 
void ScaraJoint::moveBy(float deltaDeg) {
    float spd = stepsPerDegree();
    if (spd == 0.0f) return;
 
    // Carry rounding leftover from previous move to avoid drift.
    float desiredSteps = deltaDeg * spd + stepResidual;
    long stepsToEmit = lroundf(desiredSteps);
 
    stepper.step(stepsToEmit);
    stepResidual = desiredSteps - stepsToEmit;
    currentAngle += deltaDeg;
}
 
void ScaraJoint::moveTo(float angleDeg) {
    moveBy(angleDeg - currentAngle);
}

/*void ScaraJoint::home(float backoffDeg) {
    Serial.println("Joint: homing to MIN switch");

    bool dirMin = false;
    bool dirMax = true;

    // Go toward min switch
    stepper.setDirection(dirMin);
    while (!minSwitch.isTriggered()) {

        // checking if wrong direction
        if (maxSwitch.isTriggered()) {
            Serial.println("Joint: wrong direction, reversing");
            dirMin = true;
            dirMax = false;
            stepper.setDirection(dirMin);  // flip
        }

        stepper.step();
    }

    stepper.resetPosition();
    stepper.setDirection(dirMax);
    moveBy(backoffDeg);
    stepper.resetPosition();
    min_Angle = 0.0f;

    Serial.println("Joint: homing to MAX switch");

    // Go toward max switch
    stepper.setDirection(dirMax);
    while (!maxSwitch.isTriggered()) {
        stepper.step();
    }

    stepper.setDirection(dirMin);
    moveBy(backoffDeg);

    max_Angle = angle();

    stepper.setStepDelay(200);
    Serial.println("Joint: home done.");
}
    */


