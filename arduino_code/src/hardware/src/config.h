#ifndef CONFIG_H
#define CONFIG_H

const unsigned int DEFAULT_STEP_DELAY_US = 800;

// Motor
const int MICROSTEPS = 16;
const float STEPS_PER_REV  = 200.0f;

// Gear ratios
const int   DRIVING_TEETH_j1 = 18;
const int   DRIVING_TEETH_j2 = 20;
const int   JOINT_TEETH = 105;
const int   BASE_TEETH = 160;

const float GEAR_RATIO_J1 = (float)DRIVING_TEETH_j1 / JOINT_TEETH;
const float GEAR_RATIO_J2 = (float)DRIVING_TEETH_j2 / BASE_TEETH;

// Arm link lengths (mm)
const float LINK1_LENGTH = 250.0f;
const float LINK2_LENGTH = 250.0f;
const float LINK3_LENGTH = 290.0f;  // lead screw / Z

// Lead screw
const float Z_MAX_MM = LINK3_LENGTH;
const float Z_MM_PER_REV = 15.0f;
const float GRIPPER_LENGTH  = 100.0f;

// Gripper
const int OPEN_ANGLE = 0;
const int CLOSED_ANGLE = 90;

#endif

