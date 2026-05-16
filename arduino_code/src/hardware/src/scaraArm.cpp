#include "scaraArm.h"
#include "config.h"

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
    beforeMove();

    Serial.println("Gripper openned for calibration");
    gripper.open();

    Serial.println("Calbrating lead screw");
    leadScrew.calibrate();
    Serial.println("Lead screw calibration complete");
    leadScrew.moveBy_mm(60.0f); //go up to clear king and box during rest of calibration

    Serial.println("Calibrating base joint");
    //set new soft limits
    joint1.calibrate();
    Serial.println("Base joint calibration complete");
    joint1.moveBy(137.0f);
    joint1.setZero();
    joint1.setMinAngle(-137.0f);
    joint1.setMaxAngle(137.0f);

    Serial.println("Calibrating forearm joint");
    joint2.calibrate();
    Serial.println("Forearm joint calibration complete");
    //once j1 is calibrated need to move it in the middle so it straight along the axis
    joint2.moveTo(joint2.maxAngleDeg() / 2.0f);
    joint2.setZero(); // set zero to the middle of the range so IK is centered on straight configuration
    joint2.setMinAngle(-joint2.maxAngleDeg() / 2.0f -2);
    joint2.setMaxAngle(joint2.maxAngleDeg() / 2.0f + 2);

    sync();
    Serial.println("Calibration done");

    afterMove();
}

void ScaraArm::goHome() {
    beforeMove();
    leadScrew.moveTo_mm(PICKPLACE_HOVER_Z_MM);
    joint1.moveTo(0.0f);
    joint2.moveTo(0.0f);
    afterMove();
    sync();
}

bool ScaraArm::moveXY(float x, float y) {
    IKResult r = ik.inverseKinematics(x, y);
    if (!r.reachable) { Serial.println("out of reach"); return false; }

    beforeMove();
    // Sweep j1 fully to its target, then sweep j2 fully. The arm traces an
    // arc (j1) then a second arc (j2) rather than a straight Cartesian line.
    joint1.moveTo(r.theta1);
    // joint2 motor is mounted with its positive direction opposite to the
    // IK CCW convention, so negate the commanded angle.
    joint2.moveTo(-r.theta2);
    afterMove();

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

void ScaraArm::moveZ(float mm)   { 
    beforeMove();
    leadScrew.moveTo_mm(mm); 
    afterMove();
}
void ScaraArm::moveByZ(float mm) {
    beforeMove();
    leadScrew.moveBy_mm(mm); 
    afterMove();
}

bool ScaraArm::moveXYZ(float x, float y, float z) {
    beforeMove();
    leadScrew.moveTo_mm(z);
    bool result = moveXY(x, y);
    afterMove();
    return result;
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

bool ScaraArm::pickAt(float x, float y, int pieceType) {
    // Clamp piece type to valid range
    if (pieceType < 0 || pieceType > 5) pieceType = 0;
    
    // Move to hover above target (sets Z then XY).
    if (!moveXYZ(x, y, PICKPLACE_HOVER_Z_MM)) return false;

    // Lower to piece-specific pick height and close gripper
    moveZ(PICK_Z[pieceType]);
    delay(200);
    closeGripper();

    // Lift back to safe hover/travel Z
    moveZ(PICKPLACE_HOVER_Z_MM);
    delay(200);
    return true;
}

bool ScaraArm::putAt(float x, float y, int pieceType) {
    // Clamp piece type to valid range
    if (pieceType < 0 || pieceType > 5) pieceType = 0;
    
    // Move to hover above target
    if (!moveXYZ(x, y, PICKPLACE_HOVER_Z_MM)) return false;

    // Lower to piece-specific place height and open gripper
    moveZ(PLACE_Z[pieceType]);
    delay(200);
    openGripper();

    // Retreat to safe hover/travel Z
    moveZ(PICKPLACE_HOVER_Z_MM);
    delay(200);
    return true;
}
