#include "scaraArm.h"

ScaraArm::ScaraArm(ScaraJoint& joint1, ScaraJoint& joint2, LeadScrew& leadScrew, 
    Gripper& gripper, float j1Length, float j2Length): 
    joint1(joint1),
    joint2(joint2),
    leadScrew(leadScrew),
    gripper(gripper),
    ik(j1Length, j2Length) {
         this->currentX = 0;
         this->currentY = 0;
         this->currentTheta1 = 0;
         this->currentTheta2 = 0;
    }

void ScaraArm::begin() {
    joint1.begin();
    joint2.begin();
    leadScrew.begin();
    gripper.begin();
}

void ScaraArm::calibrate() {
    Serial.println("Gripper openned for calibration");
    gripper.open();


    Serial.println("Calbrating lead screw");
    leadScrew.calibrate();
    leadScrew.moveBy_mm(60.0f); //go up to clear king and box during rest of calibration


    Serial.println("Calibrating base joint");
    //set new soft limits 
    joint1.calibrate();
    joint1.moveBy(137.0f);
    joint1.setZero();
    joint1.setMinAngle(-137.0f);
    joint1.setMaxAngle(137.0f);


    Serial.println("Calibrating forearm joint");
    joint2.calibrate();
    //once j1 is calibrated need to move it in the middle so it straight along the axis
    joint2.moveTo(joint2.maxAngleDeg() / 2.0f);
    joint2.setZero(); // set zero to the middle of the range so IK is centered on straight configuration
    joint2.setMinAngle(-joint2.maxAngleDeg() / 2.0f -2);
    joint2.setMaxAngle(joint2.maxAngleDeg() / 2.0f + 2);



    sync();
    Serial.println("Calibration done");
}

bool ScaraArm::moveXY(float x, float y) {
    IKResult finalIK = ik.inverseKinematics(x, y);
    if (!finalIK.reachable) { Serial.println("out of reach"); return false; }

    // Subdivide the Cartesian path into ~1 mm substeps so the two joints'
    // sequential moveTo calls never lag enough to bend the trajectory.
    const float STEP_MM = 1.0f;
    float startX = currentX;
    float startY = currentY;
    float dx = x - startX;
    float dy = y - startY;
    float dist = sqrt(dx * dx + dy * dy);
    int nSteps = (int)ceil(dist / STEP_MM);
    if (nSteps < 1) nSteps = 1;

    for (int i = 1; i <= nSteps; i++) {
        float t  = (float)i / (float)nSteps;
        float xi = startX + dx * t;
        float yi = startY + dy * t;
        IKResult r = ik.inverseKinematics(xi, yi);
        if (!r.reachable) {
            Serial.println("intermediate substep out of reach");
            sync();
            return false;
        }
        joint1.moveTo(r.theta1);
        // joint2 motor is mounted with its positive direction opposite to the
        // IK CCW convention, so negate the commanded angle.
        joint2.moveTo(-r.theta2);
    }

    sync();
    return true;
}



void ScaraArm::sync() {
    FKResult pos = ik.forwardKinematics(joint1.angle(), -joint2.angle());

    currentX = pos.x;
    currentY = pos.y;
    currentTheta1 = joint1.angle();
    currentTheta2 = -joint2.angle();
}

void ScaraArm::moveZ(float mm)   { leadScrew.moveTo_mm(mm); }
void ScaraArm::moveByZ(float mm) { leadScrew.moveBy_mm(mm); }

bool ScaraArm::moveXYZ(float x, float y, float z) {
    leadScrew.moveTo_mm(z);
    return moveXY(x, y);
}

void ScaraArm::moveJ1(float deg) { joint1.moveTo(deg); sync(); }
void ScaraArm::moveJ2(float deg) { joint2.moveTo(deg); sync(); }

void ScaraArm::openGripper()              { gripper.open(); }
void ScaraArm::closeGripper()             { gripper.close(); }
void ScaraArm::setGripperAngle(float deg) { gripper.goToAngle(deg); }
bool ScaraArm::gripperOpen() const        { return gripper.isOpen(); }

float ScaraArm::z() const        { return leadScrew.position_mm(); }
float ScaraArm::j1Angle() const  { return joint1.angle(); }
float ScaraArm::j2Angle() const  { return joint2.angle(); }
