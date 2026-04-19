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

// Limit switch pins (Arduino Mega 2560)
const int X_LIMIT_MIN_PIN  = 9;
const int X_LIMIT_MAX_PIN  = 10;

const int Y_LIMIT_MIN_PIN  = 11;
const int Y_LIMIT_MAX_PIN  = 12;

const int Z_LIMIT_BOTTOM_PIN = 13;

#endif