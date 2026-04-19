#include "leadScrew.h"
#include "config.h"

LeadScrew::LeadScrew(StepperXYZ& stepper, uint8_t bottomLimitPin, float stepsPerMM, 
                    float maxTravel_mm, float gripperLength) 
    : stepper(stepper) {
    this->bottomLimitPin = bottomLimitPin;
    this->stepsPerMM = stepsPerMM;
    this->maxTravel_mm = maxTravel_mm;
    this->gripperLength = gripperLength;
    pinMode(bottomLimitPin, INPUT_PULLUP);
}

bool LeadScrew::bottomHit() const {
    return digitalRead(bottomLimitPin) == LOW;
}

bool LeadScrew::wouldExceedTop(float mm) const {
    return mm > maxTravel_mm;
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
    float carriageZ = mm + gripperLength;

    if (wouldExceedTop(carriageZ)) {
        Serial.print(mm);
        Serial.print(" mm exceeds max travel ");
        Serial.print(maxTravel_mm);
        Serial.println("; Move cancelled");
        
        return;
    }

    if (carriageZ < 0) {
        Serial.println("Z: target below 0,; Move cancelled");
        return;
    }

    long target  = (long)(carriageZ * stepsPerMM);
    long steps   = target - stepper.position();
    stepper.step(steps);
}

void LeadScrew::moveBy_mm(float mm) {
    moveTo_mm(position_mm() + mm);
}

float LeadScrew::position_mm() const {
    return (stepper.position() / stepsPerMM) - gripperLength;
}