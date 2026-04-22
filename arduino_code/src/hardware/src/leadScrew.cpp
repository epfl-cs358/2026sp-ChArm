#include "leadScrew.h"

/*LeadScrew::LeadScrew(StepperXYZ& stepper, LimitSwitch& bottomSwitch, float stepsPerMM, 
                    float maxTravel_mm, float gripperLength) 
    : stepper(stepper), bottomSwitch(bottomSwitch) {
    this->stepsPerMM = stepsPerMM;
    this->maxTravel_mm = maxTravel_mm;
    this->gripperLength = gripperLength;
}
    */

LeadScrew::LeadScrew(StepperXYZ& stepper, float stepsPerMM, 
                     float gripperLength ) 
    : stepper(stepper) {
    this->stepsPerMM = stepsPerMM;
    this->gripperLength = gripperLength;
}

void LeadScrew::moveTo_mm(float mm) {
    float carriageZ = mm; //+ gripperLength;

    /*
    if (wouldExceedTop(carriageZ)) {
        Serial.print(mm);
        Serial.print(" mm exceeds max travel ");
        Serial.print(maxTravel_mm);
        Serial.println("; Move cancelled");
        
        return;
    }
        */

    if (carriageZ < 0) {
        Serial.println("Z: target below 0,; Move cancelled");
        return;
    }

    long target  = (long)(carriageZ * stepsPerMM);
    stepper.step(target);
}



void LeadScrew::moveBy_mm(float mm) {

    return 
    // TODO need to check this seems wrong at first glance 
    moveTo_mm(position_mm() + mm);
}

float LeadScrew::position_mm() const {
    return (stepper.position() / stepsPerMM); // - gripperLength;
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
