#ifndef STEPPER_XYZ_H
#define STEPPER_XYZ_H

#include <Arduino.h>

// Drives a single stepper axis through a CNC-shield-style STEP/DIR interface.
// The shared CNC shield ENABLE pin is handled separately (see pins.h).
class StepperXYZ {
public:
    StepperXYZ(uint8_t stepPin, uint8_t dirPin);
 
    void begin();
 
    // Emit one STEP pulse in the currently selected direction.
    void step();
 
    // Emit |steps| pulses; sign selects direction.
    void step(long steps);
 
    void setDirection(bool forward);
    bool direction() const { return forward; }
    void toggleDirection() { setDirection(!forward); }
    // Half-period of the STEP pulse in microseconds (total period = 2 * us).
    void setStepDelay(unsigned int microseconds);
    unsigned int stepDelay() const { return stepDelayUs; }
 
private:
    uint8_t stepPin;
    uint8_t dirPin;
    unsigned int stepDelayUs;
    bool forward;
};

#endif
