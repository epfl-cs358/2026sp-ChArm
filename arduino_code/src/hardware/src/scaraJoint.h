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
               float gearRatio);
 
    void moveTo(float angleDeg);
    void moveBy(float deltaDeg);
 
    float angle() const { return currentAngle; }
    
 
    // Called by calibration after homing to set the soft limit
    void setZero() { currentAngle = 0.0f; stepResidual = 0.0f; }
    void setAngle(float deg) { currentAngle = deg; stepResidual = 0.0f; }
    void setMinAngle(float deg) { minAngle = deg; }
    void setMaxAngle(float deg) { maxAngle = deg; }
 
    float stepsPerDegree() const;

private:
    StepperXYZ&  stepper_;
    float stepsPerRev;
    int microstep;
    float gearRatio;
    float currentAngle;
    float stepResidual; // carries sub-step rounding leftover between moves
    float minAngle;
    float maxAngle;
};

#endif
