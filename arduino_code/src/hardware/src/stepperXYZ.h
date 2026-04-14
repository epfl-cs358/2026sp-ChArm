#ifndef STEPPER_XYZ_H
#define STEPPER_XYZ_H

#include <Arduino.h>

// Drives a single stepper axis through a CNC-shield-style STEP/DIR interface.
// The shared CNC shield ENABLE pin is handled separately (see pins.h).
class StepperXYZ {
public:
    StepperXYZ(uint8_t stepPin, uint8_t dirPin, uint8_t microstep = 1);

    void begin();

    // Emit one STEP pulse in the currently selected direction.
    void step();

    // Emit |steps| pulses; sign selects direction.
    void step(long steps);

    void setDirection(bool forward);
    bool direction() const { return forward; }

    // Half-period of the STEP pulse in microseconds (total period = 2 * us).
    void setStepDelay(unsigned int microseconds);
    unsigned int stepDelay() const { return stepDelayUs; }

    uint8_t microstep() const { return microstepValue; }

    long position() const { return positionSteps; }
    void resetPosition() { positionSteps = 0; }

private:
    uint8_t stepPin;
    uint8_t dirPin;
    uint8_t microstepValue;
    unsigned int stepDelayUs;
    long positionSteps;
    bool forward;
};

#endif
