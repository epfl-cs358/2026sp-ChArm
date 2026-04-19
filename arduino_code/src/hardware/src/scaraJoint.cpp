#include "scaraJoint.h"
#include <math.h>

ScaraJoint::ScaraJoint(StepperXYZ& stepper, uint8_t minPin, uint8_t maxPin,
                        float stepsPerRev, float gearRatio)
    : stepper(stepper) {
    this->minPin = minPin;
    this->maxPin = maxPin;
    this->stepsPerRev = stepsPerRev;
    this->gearRatio = gearRatio;
    this->min_Angle = 0.0f;
    this->max_Angle = 0.0f;
    this->homed = false;
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
    if (!homed) {
        Serial.println("Joint: not homed yet — run home() first.");
        return;
    }

    if (angleDeg < min_Angle || angleDeg > max_Angle) {
        Serial.print("Joint: target ");
        Serial.print(angleDeg);
        Serial.print(" deg out of range [");
        Serial.print(min_Angle);
        Serial.print(", ");
        Serial.print(max_Angle);
        Serial.println("] — move cancelled.");
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
    homed = false;

    Serial.println("Joint: homing — seeking MIN limit switch");

    long backoffSteps = lroundf(backoffDeg * stepsPerDegree());

    // ── Phase 1: move toward MIN limit switch ──────────────────────────────
    // Direction convention: false = toward min, true = toward max.
    // If the MAX switch is hit before the MIN switch the motor is wired in
    // reverse; print an error and abort so the operator can fix the wiring.
    stepper.setDirection(false);
    while (digitalRead(minPin) == HIGH) {
        if (digitalRead(maxPin) == LOW) {
            Serial.println("Joint: ERROR — hit MAX switch while seeking MIN.");
            Serial.println("Joint: Reverse motor wiring or swap MIN/MAX switch pins, then retry homing.");
            return;
        }
        stepper.step();
    }

    // Back off from MIN switch so the switch is released during normal travel.
    stepper.resetPosition();
    stepper.setDirection(true);
    for (long i = 0; i < backoffSteps; i++) {
        stepper.step();
    }
    stepper.resetPosition();
    min_Angle = 0.0f;

    // ── Phase 2: sweep to MAX limit switch to measure full range ───────────
    Serial.println("Joint: seeking MAX limit switch");

    stepper.setDirection(true);
    while (digitalRead(maxPin) == HIGH) {
        stepper.step();
    }

    // Back off from MAX switch.
    stepper.setDirection(false);
    for (long i = 0; i < backoffSteps; i++) {
        stepper.step();
    }

    max_Angle = angle();
    homed = true;

    Serial.print("Joint: homed. Range [0, ");
    Serial.print(max_Angle);
    Serial.println("] deg");
}

void ScaraJoint::checkLimits() {
    if (digitalRead(minPin) == LOW && !stepper.direction()) {
        Serial.println("Joint: MIN limit hit!");
    }

    if (digitalRead(maxPin) == LOW && stepper.direction()) {
        Serial.println("Joint: MAX limit hit!");
    }
}

