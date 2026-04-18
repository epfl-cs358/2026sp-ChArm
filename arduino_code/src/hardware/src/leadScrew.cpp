#include "leadScrew.h"
#include "config.h"

LeadScrew::LeadScrew(StepperXYZ& stepper, uint8_t bottomLimitPin) 
    : stepper(stepper) {
    this->bottomLimitPin = bottomLimitPin;
    pinMode(bottomLimitPin, INPUT_PULLUP);
}

bool LeadScrew::bottomHit() const {
    return digitalRead(bottomLimitPin) == LOW;
}

bool LeadScrew::wouldExceedTop(float mm) const {
    return mm > Z_MAX_MM;
}

void LeadScrew::home(float backoff_mm) {
    Serial.println("Z: moving to bottom");

    // Stop the program and flip
    // if motor goes wrong way
    stepper.setDirection(false);
    stepper.setStepDelay(800);

    while (!bottomHit()) {
        stepper.step();
    }

    stepper.resetPosition();
    moveBy_mm(backoff_mm);
    stepper.resetPosition();

    stepper.setStepDelay(200);
    Serial.println("Z: home done.");
}

void LeadScrew::moveTo_mm(float mm) {
    if (wouldExceedTop(mm)) {
        Serial.print(mm);
        Serial.print(" mm exceeds max travel ");
        Serial.print(Z_MAX_MM);
        Serial.println("; Move cancelled");
        
        return;
    }

    if (mm < 0) {
        Serial.println("Z: target below 0,; Move cancelled");
        return;
    }

    long target  = (long)(mm * Z_MM_PER_REV);
    long steps   = target - stepper.position();
    stepper.step(steps);
}

void LeadScrew::moveBy_mm(float mm) {
    moveTo_mm(position_mm() + mm);
}

float LeadScrew::position_mm() const {
    return stepper.position() / Z_MM_PER_REV;
}