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
    ScaraJoint(StepperXYZ& stepper,
               float stepsPerRev,
               int microstep,
               float gearRatio,
               LimitSwitch& limSwitch,
                bool isdualLimit);

    // Initializes the underlying stepper and limit switch pins.
    void begin();

    void moveTo(float angleDeg);
    void moveBy(float deltaDeg);

    // Returns the current angle in degrees, as tracked by the class. This is not
    float angle() const { return currentAngle; }
    // Sets the current angle to zero without moving the motor, for use after calibration.
    void setZero() { currentAngle = 0.0f; stepResidual = 0.0f; }
    // Sets the current angle to a set angle without moving the motor, for use after calibration.
    void setAngle(float deg) { currentAngle = deg; stepResidual = 0.0f; }
    
    //set soft limits for the joint, which will be enforced by moveTo and moveBy. These are relative to the zero position set during calibration.
    void setMinAngle(float deg) { minAngle = deg; }
    void setMaxAngle(float deg) { maxAngle = deg; }

    float stepsPerDegree() const;
    float minAngleDeg() const { return minAngle; }
    float maxAngleDeg() const { return maxAngle; }
    void calibrate();

private:
    StepperXYZ&  stepper_;
    LimitSwitch& limitSwitch;
    float stepsPerRev;
    int microstep;
    float gearRatio;
    float currentAngle;
    float stepResidual;
    float minAngle;
    float maxAngle;
    bool isDualLimit;
};

#endif
