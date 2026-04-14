#include "stepperXYZ.h"

static const unsigned int DEFAULT_STEP_DELAY_US = 200;

StepperXYZ::StepperXYZ(uint8_t stepPin, uint8_t dirPin, uint8_t microstep) {
    this->stepPin = stepPin;
    this->dirPin = dirPin;
    this->microstepValue = (microstep == 0) ? 1 : microstep;
    this->stepDelayUs = DEFAULT_STEP_DELAY_US;
    this->positionSteps = 0;
    this->forward = true;
}

void StepperXYZ::begin() {
    pinMode(stepPin, OUTPUT);
    pinMode(dirPin, OUTPUT);
    digitalWrite(stepPin, LOW);
    digitalWrite(dirPin, forward ? HIGH : LOW);
}

void StepperXYZ::setDirection(bool forward) {
    this->forward = forward;
    digitalWrite(dirPin, forward ? HIGH : LOW);
}

void StepperXYZ::setStepDelay(unsigned int microseconds) {
    stepDelayUs = microseconds;
}

void StepperXYZ::step() {
    digitalWrite(stepPin, HIGH);
    delayMicroseconds(stepDelayUs);
    digitalWrite(stepPin, LOW);
    delayMicroseconds(stepDelayUs);
    positionSteps += forward ? 1 : -1;
}

void StepperXYZ::step(long steps) {
    if (steps == 0) return;
    setDirection(steps > 0);
    long count = steps > 0 ? steps : -steps;
    for (long i = 0; i < count; ++i) {
        step();
    }
}
