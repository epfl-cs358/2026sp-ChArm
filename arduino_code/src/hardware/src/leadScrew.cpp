#include "leadScrew.h"

LeadScrew::LeadScrew(StepperXYZ& stepper, float stepsPerMM, float gripperLength)
    : stepper(stepper) {
    this->stepsPerMM = stepsPerMM;
    this->gripperLength = gripperLength;
    this->currentMm = 0.0f;
    this->stepResidual = 0.0f;
}
 
void LeadScrew::moveBy_mm(float deltaMm) {
    float spm = stepsPerMM;
    if (spm == 0.0f) return;
 
    if (currentMm + deltaMm < 0) {
        Serial.println("Z: target below 0; Move cancelled");
        return;
    }
 
    // Carry rounding leftover from previous move to avoid drift.
    float desiredSteps = deltaMm * spm + stepResidual;
    long stepsToEmit = lroundf(desiredSteps);
 
    stepper.step(stepsToEmit);
    stepResidual = desiredSteps - stepsToEmit;
    currentMm += deltaMm;
}
 
void LeadScrew::moveTo_mm(float mm) {
    moveBy_mm(mm - currentMm);
}

/*bool LeadScrew::wouldExceedTop(float mm) const {
    return mm > maxTravel_mm;
}
*/

/*void LeadScrew::home(float backoff_mm) {
    Serial.println("Z: moving to bottom");

    // Stop the program and flip
    // if motor goes wrong way
    stepper.setDirection(false);
    stepper.setStepDelay(800);

    while (!bottomSwitch.isTriggered()) { stepper.step(); }

    stepper.resetPosition();
    moveBy_mm(backoff_mm);
    stepper.resetPosition();

    stepper.setStepDelay(200);
    Serial.println("Z: home done.");
}
    */
