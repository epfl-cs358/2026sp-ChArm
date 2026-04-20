#ifndef SCARA_JOINT_H
#define SCARA_JOINT_H

#include "stepperXYZ.h"
#include "limitSwitch.h"
#include <Arduino.h>

// Angle-based wrapper around a StepperXYZ axis, intended for SCARA joints.
// Converts degrees to steps using the motor's native resolution,
// its microstep setting, and any mechanical gear reduction.
class ScaraJoint {
public:
    ScaraJoint(StepperXYZ&  stepper,
               LimitSwitch& minSwitch,
               LimitSwitch& maxSwitch,
               float stepsPerRev,
               float gearRatio);

    void moveTo(float angleDeg);
    void moveBy(float deltaDeg);

    float angle() const;
    float minAngle() const { return min_Angle; }
    float maxAngle() const { return max_Angle; }

    void setZero() { stepper.resetPosition(); }

    float stepsPerDegree() const;

    void home(float backoffDeg = 5.0f);

private:
    StepperXYZ&  stepper;
    LimitSwitch& minSwitch;
    LimitSwitch& maxSwitch;
    float stepsPerRev;
    float gearRatio;
    float min_Angle;
    float max_Angle;
};

#endif
