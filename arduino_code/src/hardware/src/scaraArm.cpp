#include "scaraArm.h"

ScaraArm::ScaraArm(ScaraJoint& joint1, ScaraJoint& joint2, float j1Length, float j2Length): 
    joint1(joint1),
    joint2(joint2),
    ik(j1Length, j2Length) {}

void ScaraArm::moveXY(float x, float y) {
    IKResult result = ik.inverseKinematics(x, y);
    if (!result.reachable) { Serial.println("out of reach"); return; }

    joint1.moveTo(result.theta1);
    joint2.moveTo(result.theta2);

    currentX = x; 
    currentY = y;
    currentTheta1 = result.theta1; 
    currentTheta2 = result.theta2;
}

void ScaraArm::sync() {
    FKResult pos = ik.forwardKinematics(joint1.angle(), joint2.angle());
    
    currentX = pos.x; 
    currentY = pos.y;
    currentTheta1 = joint1.angle(); 
    currentTheta2 = joint2.angle();
}
