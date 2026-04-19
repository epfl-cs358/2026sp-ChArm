#ifndef SCARA_JOINT_H
#define SCARA_JOINT_H

#include "stepperXYZ.h"
#include <Arduino.h>

// Angle-based wrapper around a StepperXYZ axis, intended for SCARA joints.
// Converts degrees to steps using the motor's native resolution,
// its microstep setting, and any mechanical gear reduction.
class ScaraJoint {
public:
    ScaraJoint(StepperXYZ& stepper,
                uint8_t minPin,
                uint8_t maxPin,
                float stepsPerRev,
                float gearRatio);

    void moveTo(float angleDeg);
    void moveBy(float deltaDeg);

    float angle() const;
    float minAngle() const { return min_Angle; }
    float maxAngle() const { return max_Angle; }

    void setZero() { stepper.resetPosition(); }

    float stepsPerDegree() const;

    // Home the joint using its two limit switches.
    // Moves to the MIN switch to establish the zero position, then sweeps to
    // the MAX switch to record the full travel range.
    // backoffDeg: degrees to retreat from each switch so the switch is not
    //             held pressed during normal operation.
    void home(float backoffDeg = 5.0f);

    // Returns true after a successful home() sequence.
    bool isHomed() const { return homed; }

    void checkLimits();

private:
    StepperXYZ& stepper;
    uint8_t minPin;
    uint8_t maxPin;
    float stepsPerRev;
    float gearRatio;
    float min_Angle;
    float max_Angle;
    bool  homed;
};

#endif
