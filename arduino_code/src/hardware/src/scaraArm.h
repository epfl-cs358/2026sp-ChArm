#ifndef SCARA_ARM_H
#define SCARA_ARM_H

#include "scaraJoint.h"
#include "scaraKinematics.h"
#include <Arduino.h>
#include "leadScrew.h"
#include "gripper.h"
#include "enableDriver.h"
// Ties two ScaraJoints together with a ScaraKinematics solver.
// Lets the caller move the end effector in Cartesian (x, y) space.
class ScaraArm {
public:
    ScaraArm(ScaraJoint& joint1,
            ScaraJoint& joint2,
            LeadScrew& leadScrew,
            Gripper& gripper,
            float j1Length,
            float j2Length);

    // Solve IK for (x, y) and drive both joints to the resulting angles.
    // No-op if the target is out of reach.
    bool moveXY(float x, float y);

    // Z axis (lead screw). Absolute and relative.
    void moveZ(float mm);
    void moveByZ(float mm);

    // Combined XYZ. Returns false if XY is out of reach (Z has already moved).
    bool moveXYZ(float x, float y, float z);

    // Joint-level moves (motor-frame angles). Syncs cached pose afterwards.
    void moveJ1(float deg);
    void moveJ2(float deg);

    // Gripper passthroughs.
    void openGripper();
    void closeGripper();
    void setGripperAngle(float deg);
    bool gripperOpen() const;

    // High-level pick and place helpers using preset Z heights per piece type.
    bool pickAt(float x, float y, int pieceType);
    bool putAt(float x, float y, int pieceType);

    float theta1() const { return currentTheta1; }
    float theta2() const { return currentTheta2; }
    float x() const { return currentX; }
    float y() const { return currentY; }
    float z() const;
    float j1Angle() const;
    float j2Angle() const;

    // Initializes joints, lead screw, and gripper (pinModes and stepper state).
    void begin();

    void sync();
    void calibrate();
    void goHome();

private:
    ScaraJoint& joint1;
    ScaraJoint& joint2;
    LeadScrew& leadScrew;
    Gripper& gripper;
    ScaraKinematics ik;
    float currentX;
    float currentY;
    float currentTheta1;
    float currentTheta2;
};

#endif
