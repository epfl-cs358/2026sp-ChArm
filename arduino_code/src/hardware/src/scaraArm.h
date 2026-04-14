#ifndef SCARA_ARM_H
#define SCARA_ARM_H

#include "scaraJoint.h"
#include "scaraKinematics.h"

// Ties two ScaraJoints together with a ScaraKinematics solver.
// Lets the caller move the end effector in Cartesian (x, y) space.
class ScaraArm {
public:
    ScaraArm(ScaraJoint& joint1,
            ScaraJoint& joint2,
            float j1Length,
            float j2Length);

    // Solve IK for (x, y) and drive both joints to the resulting angles.
    // No-op if the target is out of reach.
    void moveXY(float x, float y);

    float theta1() const { return ik.theta1(); }
    float theta2() const { return ik.theta2(); }

private:
    ScaraJoint& joint1;
    ScaraJoint& joint2;
    ScaraKinematics ik;
};

#endif
