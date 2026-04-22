#include "stepperXYZ.h"
#include "config.h"

StepperXYZ::StepperXYZ(uint8_t stepPin, uint8_t dirPin) {
    this->stepPin = stepPin;
    this->dirPin = dirPin;
    this->stepDelayUs = DEFAULT_STEP_DELAY_US;
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
}
 
void StepperXYZ::step(long steps) {
    if (steps == 0) return;
    setDirection(steps > 0);
    long count = labs(steps);
    for (long i = 0; i < count; ++i) {
        step();
    }
}