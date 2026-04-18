#include "scaraJoint.h"
#include <math.h>

ScaraJoint::ScaraJoint(StepperXYZ& stepper, uint8_t minPin, uint8_t maxPin,
                        float stepsPerRev, float gearRatio)
    : stepper(stepper) {
    this->minPin = minPin;
    this->maxPin = maxPin;
    this->stepsPerRev = stepsPerRev;
    this->gearRatio = gearRatio;
    pinMode(minPin, INPUT_PULLUP);
    pinMode(maxPin, INPUT_PULLUP);
}

float ScaraJoint::stepsPerDegree() const {
    return (stepsPerRev * stepper.microstep() * gearRatio) / 360.0f;
}

float ScaraJoint::angle() const {
    float spd = stepsPerDegree();
    if (spd == 0.0f) return 0.0f;
    return stepper.position() / spd;
}

void ScaraJoint::moveTo(float angleDeg) {
    if (max_Angle == 0.0f) {
        Serial.println("Joint: not homed yet!");
        return;
    }

    if (angleDeg < min_Angle || angleDeg > max_Angle) {
        Serial.print("Joint: out of bound position; ");
        Serial.println("Move cancelled.");
        return;
    }

    long targetSteps = lroundf(angleDeg * stepsPerDegree());
    long steps = targetSteps - stepper.position();
    stepper.step(steps);
}

void ScaraJoint::moveBy(float deltaDeg) {
    moveTo(angle() + deltaDeg);
}

void ScaraJoint::home(float backoffDeg) {
    Serial.println("Joint: homing to MIN switch");

    bool dirMin = false;
    bool dirMax = true;

    // Go toward min switch
    stepper.setDirection(dirMin);
    while (digitalRead(minPin) == HIGH) {

        // checking if wrong direction
        if (digitalRead(maxPin) == LOW) {
            Serial.println("Joint: wrong direction, reversing");
            dirMin = true;
            dirMax = false;
            stepper.setDirection(dirMin);  // flip
        }

        stepper.step();
    }

    stepper.resetPosition();
    stepper.setDirection(dirMax);
    moveBy(backoffDeg);
    stepper.resetPosition();
    min_Angle = 0.0f;

    Serial.println("Joint: homing to MAX switch");

    // Go toward max switch
    stepper.setDirection(dirMax);
    while (digitalRead(maxPin) == HIGH) {
        stepper.step();
    }

    stepper.setDirection(dirMin);
    moveBy(backoffDeg);

    max_Angle = angle();

    stepper.setStepDelay(200);
    Serial.println("Joint: home done.");
}

void ScaraJoint::checkLimits() {
    if (digitalRead(minPin) == LOW && !stepper.direction()) {
        Serial.println("Joint: MIN limit hit!");
    }

    if (digitalRead(maxPin) == LOW && stepper.direction()) {
        Serial.println("Joint: MAX limit hit!");
    }
}


