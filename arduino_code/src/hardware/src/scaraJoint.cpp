#include "scaraJoint.h"
#include <math.h>

ScaraJoint::ScaraJoint(StepperXYZ& stepper, LimitSwitch& minSwitch, LimitSwitch& maxSwitch, 
                        float stepsPerRev, float gearRatio)
    : stepper(stepper), minSwitch(minSwitch), maxSwitch(maxSwitch) {
    this->stepsPerRev = stepsPerRev;
    this->gearRatio = gearRatio;
    this->max_Angle = 0.0f;
    this->min_Angle = 0.0f;
}

float ScaraJoint::stepsPerDegree() const {
    return (stepsPerRev * stepper.microstep() * gearRatio) / 360.0f;
}

float ScaraJoint::angle() const {
    float spd = stepsPerDegree();
    if (spd == 0.0f) return 0.0f;
    return stepper.position() / spd;
}

void ScaraJoint::moveTo(float angleDeg) {
    if (max_Angle == 0.0f) {
        Serial.println("Joint: not homed yet!");
        return;
    }

    if (angleDeg < min_Angle || angleDeg > max_Angle) {
        Serial.print("Joint: out of bound position; ");
        Serial.println("Move cancelled.");
        return;
    }

    long targetSteps = lroundf(angleDeg * stepsPerDegree());
    long steps = targetSteps - stepper.position();
    stepper.step(steps);
}

void ScaraJoint::moveBy(float deltaDeg) {
    moveTo(angle() + deltaDeg);
}

void ScaraJoint::home(float backoffDeg) {
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


