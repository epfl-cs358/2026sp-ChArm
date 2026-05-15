#ifndef PINS_H
#define PINS_H

// stepper axis
const int X_STEP_IN1 = 2;
const int Y_STEP_IN1 = 3;
const int Z_STEP_IN1 = 4;

const int X_DIR_IN1 = 5;
const int Y_DIR_IN1 = 6;
const int Z_DIR_IN1 = 7;

const int ENABLE_PIN = 8;

// limit switches
const int X_LIMIT_PIN = 9;
const int Y_LIMIT_PIN = 10;
const int Z_LIMIT_BOTTOM_PIN = 11; 

// gripper pin
const int GRIPPER_PIN = 46;

// button pins
const int SW_PIN = 24;
const int DT_PIN = 19;
const int CLK_PIN = 18;



// lcd pins
const int RS_PIN = 44;
const int E_PIN = 42;
const int D4_PIN = 38;
const int D5_PIN = 36;
const int D6_PIN = 34;
const int D7_PIN = 32;

#endif