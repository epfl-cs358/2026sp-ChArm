#include "scaraArm.h"

ScaraArm::ScaraArm(ScaraJoint& joint1, ScaraJoint& joint2, float j1Length, float j2Length): 
    joint1(joint1),
    joint2(joint2),
    ik(j1Length, j2Length) {
         this->currentX = 0;
         this->currentY = 0;
         this->currentTheta1 = 0;
         this->currentTheta2 = 0;
    }

bool ScaraArm::moveXY(float x, float y) {
    IKResult result = ik.inverseKinematics(x, y);
    if (!result.reachable) { Serial.println("out of reach"); return false; }

    joint1.moveTo(result.theta1);
    joint2.moveTo(result.theta2);

    currentX = x; 
    currentY = y;
    currentTheta1 = result.theta1; 
    currentTheta2 = result.theta2;
    
    return true;
}

void ScaraArm::sync() {
    FKResult pos = ik.forwardKinematics(joint1.angle(), joint2.angle());

    currentX = pos.x; 
    currentY = pos.y;
    currentTheta1 = joint1.angle(); 
    currentTheta2 = joint2.angle();
}
