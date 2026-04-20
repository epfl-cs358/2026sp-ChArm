#ifndef LIMIT_SWITCH_H
#define LIMIT_SWITCH_H
 
#include <Arduino.h>
 
class LimitSwitch {
public:
    LimitSwitch(uint8_t pin, bool activeLow);
 
    void begin();
    bool isTriggered() const;
 
private:
    uint8_t pin;
    bool activeLow;
};
 
#endif