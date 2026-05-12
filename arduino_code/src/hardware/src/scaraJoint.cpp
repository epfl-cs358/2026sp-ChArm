#include "scaraJoint.h"
#include <math.h>

ScaraJoint::ScaraJoint(StepperXYZ& stepper,
                       float stepsPerRev,
                       int microstep,
                       float gearRatio,
                       LimitSwitch& limSwitch
                       , bool isdualLimit)
    : stepper_(stepper), limitSwitch(limSwitch), isDualLimit(isdualLimit) {
    this->stepsPerRev = stepsPerRev;
    this->microstep = microstep;
    this->gearRatio = gearRatio;
    this->currentAngle = 0.0f;
    this->minAngle = 0.0f;
    this->maxAngle = 360.0f;
}
 
void ScaraJoint::begin() {
    stepper_.begin();
    limitSwitch.begin();
}

float ScaraJoint::stepsPerDegree() const {
    // Uses stored microstep (not read from stepper) so it's always correct.
    return (stepsPerRev * microstep) / (gearRatio * 360.0f);
}
void ScaraJoint::calibrate() {
    Serial.println("Calibrating joint");
    // Drive towards the limit until triggered, back off, and set zero.
    stepper_.setDirection(false);
    while (!limitSwitch.pressed()) {
        stepper_.step();
    }
    //backoff until switch releases to avoid wearing it out
    stepper_.toggleDirection();
    while (limitSwitch.pressed()) {
        stepper_.step();
    }
    setZero();
    if (isDualLimit) {
        long stepsDone = 0;
        // If there's a second limit switch, use it to set the max angle.
        Serial.println("Calibrating max angle");
        while (!limitSwitch.pressed()) {
            stepper_.step();
            stepsDone++;
        }
        stepper_.toggleDirection();
        while (limitSwitch.pressed())
        {
            stepper_.step();
            stepsDone--;
        }
        float angleMoved = stepsDone / stepsPerDegree();
        setMaxAngle(angleMoved);
        setAngle(angleMoved); 
    }
}
 
void ScaraJoint::moveBy(float deltaDeg) {
    float spd = stepsPerDegree();
    if (spd == 0.0f) return;

    float target = currentAngle + deltaDeg;
    
    if (target < minAngle) {
        Serial.print("Joint: target ");
        Serial.print(target);
        Serial.print(" below min ");
        Serial.print(minAngle);
        Serial.println("; move cancelled");
        return;
    }
    if (target > maxAngle) {
        Serial.print("Joint: target ");
        Serial.print(target);
        Serial.print(" exceeds max ");
        Serial.print(maxAngle);
        Serial.println("; move cancelled");
        return;
    }               
 
    long stepsToEmit = lroundf(deltaDeg * spd);
    stepper_.step(stepsToEmit);
    // Track the physical (emitted) angle, not the commanded one, so
    // currentAngle stays in sync with the motor across many moves. Without
    // this, repeated moveXY substeps accumulate sub-step rounding error and
    // arm.x()/arm.y() drift from the true physical position — which makes
    // saved corner captures (h1, a1, h8) non-repeatable.
    currentAngle += (float)stepsToEmit / spd;
}
 
void ScaraJoint::moveTo(float angleDeg) {
    moveBy(angleDeg - currentAngle);
}
