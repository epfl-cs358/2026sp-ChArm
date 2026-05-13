#ifndef CONFIG_H
#define CONFIG_H

const unsigned int DEFAULT_STEP_DELAY_US = 600;

// Motor
const int MICROSTEPS = 16;
const float STEPS_PER_REV  = 200.0f;

// Gear ratios
const int   DRIVING_TEETH_j2 = 18;
const int   DRIVING_TEETH_j1 = 20;
const int   JOINT_TEETH = 105;
const int   BASE_TEETH = 160;

const float GEAR_RATIO_J2 = (float)DRIVING_TEETH_j2 / JOINT_TEETH;
const float GEAR_RATIO_J1 = (float)DRIVING_TEETH_j1 / BASE_TEETH;

// Arm link lengths (mm)
const float LINK1_LENGTH = 250.0f;
const float LINK2_LENGTH = 250.0f;
const float LINK3_LENGTH = 290.0f;  // lead screw / Z

// Lead screw
const float Z_MAX_MM = LINK3_LENGTH;
const float STARTS = 4.0f;
const float PITCH = 2.0f;
const float LEAD = STARTS * PITCH;
const float STEPS_PER_MM = STEPS_PER_REV * 2 / LEAD;
const float GRIPPER_LENGTH  = 100.0f;

// Gripper
const int OPEN_ANGLE = 65;
const int CLOSED_ANGLE = 0;

// Chess piece types (used for pick/place Z height lookup)
enum ChessPiece {
  PAWN = 0,
  KNIGHT = 1,
  BISHOP = 2,
  ROOK = 3,
  QUEEN = 4,
  KING = 5
};

// Pick/place Z presets per piece type (mm)
// Common hover/travel height (safe for all pieces)
const float PICKPLACE_HOVER_Z_MM = 60.0f;

// Pick Z (lower to grip) per piece type
const float PICK_Z[6] = {
  20.0f,  // PAWN
  20.0f,  // KNIGHT
  22.0f,  // BISHOP
  25.0f,  // ROOK
  28.0f,  // QUEEN
  30.0f   // KING
};

// Place Z (lower to set down) per piece type
const float PLACE_Z[6] = {
  30.0f,  // PAWN
  30.0f,  // KNIGHT
  32.0f,  // BISHOP
  35.0f,  // ROOK
  38.0f,  // QUEEN
  40.0f   // KING
};

// Trash position Z (hardcoded, not calibrated)
const float TRASH_Z = 60.0f;

#endif

