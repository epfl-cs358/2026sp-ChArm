#ifndef SCARA_JOINT_H
#define SCARA_JOINT_H

#include "stepperXYZ.h"

// Angle-based wrapper around a StepperXYZ axis, intended for SCARA joints.
// Converts degrees to steps using the motor's native resolution,
// its microstep setting, and any mechanical gear reduction.
class ScaraJoint {
public:
    ScaraJoint(StepperXYZ& stepper,
               float stepsPerRev = 200.0f,
               float gearRatio = 1.0f);

    void moveTo(float angleDeg);
    void moveBy(float deltaDeg);

    float angle() const;
    void setZero() { stepper.resetPosition(); }

    float stepsPerDegree() const;

private:
    StepperXYZ& stepper;
    float stepsPerRev;
    float gearRatio;
};

#endif
