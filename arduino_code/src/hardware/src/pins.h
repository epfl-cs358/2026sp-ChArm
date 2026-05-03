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
const int CLK_PIN;
const int DT_PIN;
const int SW_PIN;

// lcd pins
const int RS_PIN;
const int E_PIN;
const int D4_PIN;
const int D5_PIN;
const int D6_PIN;
const int D7_PIN;

#endif