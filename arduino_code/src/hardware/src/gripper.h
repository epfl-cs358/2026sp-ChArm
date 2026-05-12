#ifndef GRIPPER_H
#define GRIPPER_H

#include <Servo.h>
#include <Arduino.h>

class Gripper {
public:
    Gripper(uint8_t servoPin, int openAngle, int closedAngle);

    void begin();
    void open();
    void close();
    bool isOpen() const { return is_Open; }

    void goToAngle(float angle);

private:
    Servo servo;
    uint8_t servoPin;
    int openAngle;
    int closedAngle;
    bool is_Open;
};

#endif