#include "scaraJoint.h"
#include <math.h>

ScaraJoint::ScaraJoint(StepperXYZ& stepper, float stepsPerRev, float gearRatio)
    : stepper(stepper) {
    this->stepsPerRev = stepsPerRev;
    this->gearRatio = gearRatio;
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
    long targetSteps = lroundf(angleDeg * stepsPerDegree());
    long delta = targetSteps - stepper.position();
    stepper.step(delta);
}

void ScaraJoint::moveBy(float deltaDeg) {
    long steps = lroundf(deltaDeg * stepsPerDegree());
    stepper.step(steps);
}
