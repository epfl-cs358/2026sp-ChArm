#include "scaraArm.h"

ScaraArm::ScaraArm(ScaraJoint& joint1, ScaraJoint& joint2, float j1Length, float j2Length): 
    joint1(joint1),
    joint2(joint2),
    ik(j1Length, j2Length) {}

void ScaraArm::moveXY(float x, float y) {
    ik.inverseKinematics(x, y);
    joint1.moveTo(ik.theta1());
    joint2.moveTo(ik.theta2());
}

void ScaraArm::sync() {
    ik.forwardKinematics(joint1.angle(), joint2.angle());
}
