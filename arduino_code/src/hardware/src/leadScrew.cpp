#include "leadScrew.h"
#include "config.h"
#include <math.h>

LeadScrew::LeadScrew(StepperXYZ& stepper, uint8_t bottomLimitPin) 
    : stepper(stepper) {
    this->bottomLimitPin = bottomLimitPin;
    // steps/mm = (native steps/rev × microstep factor) / (mm/rev lead-screw pitch)
    this->stepsPerMM  = (STEPS_PER_REV * stepper.microstep()) / Z_MM_PER_REV;
    this->maxTravel_mm = Z_MAX_MM;
    this->homed = false;
    pinMode(bottomLimitPin, INPUT_PULLUP);
}

bool LeadScrew::bottomHit() const {
    return digitalRead(bottomLimitPin) == LOW;
}

bool LeadScrew::wouldExceedTop(float mm) const {
    return mm > maxTravel_mm;
}

void LeadScrew::home(float backoff_mm) {
    homed = false;

    Serial.println("Z: homing — seeking bottom limit switch");

    stepper.setDirection(false);
    stepper.setStepDelay(800);

    while (!bottomHit()) {
        stepper.step();
    }

    // Back off from the bottom switch so it is not held pressed during travel.
    long backoffSteps = lroundf(backoff_mm * stepsPerMM);
    stepper.resetPosition();
    stepper.setDirection(true);
    for (long i = 0; i < backoffSteps; i++) {
        stepper.step();
    }
    stepper.resetPosition();

    stepper.setStepDelay(200);
    homed = true;
    Serial.println("Z: homed. Position reset to 0 mm.");
}

void LeadScrew::moveTo_mm(float mm) {
    if (!homed) {
        Serial.println("Z: not homed yet — run home() first.");
        return;
    }

    if (mm < 0.0f) {
        Serial.println("Z: target below 0 mm — move cancelled.");
        return;
    }

    if (wouldExceedTop(mm)) {
        Serial.print("Z: target ");
        Serial.print(mm);
        Serial.print(" mm exceeds max travel ");
        Serial.print(maxTravel_mm);
        Serial.println(" mm — move cancelled.");
        return;
    }

    long target = lroundf(mm * stepsPerMM);
    long steps  = target - stepper.position();
    stepper.step(steps);
}

void LeadScrew::moveBy_mm(float mm) {
    moveTo_mm(position_mm() + mm);
}

float LeadScrew::position_mm() const {
    return stepper.position() / stepsPerMM;
}
