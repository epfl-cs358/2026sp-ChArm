#include <Arduino.h>
#include "hardware/src/pins.h"
#include "hardware/src/stepperXYZ.h"
#include "hardware/src/scaraJoint.h"
#include "hardware/src/leadScrew.h"
#include "hardware/src/scaraArm.h"
#include "hardware/src/config.h"
#include "hardware/src/gripper.h"
#include "hardware/src/limitSwitch.h"
#include "hardware/src/buttonInput.h"
#include "hardware/src/uiState.h"
#include "hardware/src/lcdDisplay.h"
#include "hardware/src/uiController.h"
#include "hardware/src/enableDriver.h"

StepperXYZ xStepper(X_STEP_IN1, X_DIR_IN1);
StepperXYZ yStepper(Y_STEP_IN1, Y_DIR_IN1);
StepperXYZ zStepper(Z_STEP_IN1, Z_DIR_IN1);

LimitSwitch j1Lim(X_LIMIT_PIN);
LimitSwitch j2Lim(Y_LIMIT_PIN);
LimitSwitch zLim(Z_LIMIT_BOTTOM_PIN);

ScaraJoint joint1(xStepper, STEPS_PER_REV, MICROSTEPS, GEAR_RATIO_J1, j1Lim, false); //base
ScaraJoint joint2(yStepper, STEPS_PER_REV, MICROSTEPS, GEAR_RATIO_J2, j2Lim, true); //forearm
Gripper gripper(GRIPPER_PIN, OPEN_ANGLE, CLOSED_ANGLE);
LeadScrew leadScrew(zStepper, STEPS_PER_MM, Z_MAX_MM, zLim);

ScaraArm arm(joint1, joint2, leadScrew, gripper, LINK1_LENGTH, LINK2_LENGTH);
 
UIState uiState;
ButtonInput buttonInput(CLK_PIN, DT_PIN, SW_PIN);
LCDDisplay lcd(RS_PIN, E_PIN, D4_PIN, D5_PIN, D6_PIN, D7_PIN);
UIController uiController(buttonInput, uiState, lcd, Serial1);


int stepCount = 0;
static String cmdBuffer = "";

// Cartesian jog mode: w/a/s/d move XY, u/j move Z. Toggle with `controllerMode`.
// 'd' is taken by +X in this mode, so Z-down uses 'j' (under 'u' on QWERTY).
// Steps are small so terminal key-repeat feels continuous instead of queueing.
static bool controllerMode = false;
static const float JOG_XY_MM = 3.0f;
static const float JOG_Z_MM  = 1.5f;

// Chess board calibration by 3-corner vector decomposition.
// Capture the arm's (x, y) at the centers of A1, H1, and H8. Every other
// square is then built from H1 plus integer multiples of two basis vectors:
//   vFile = (a1 - h1) / 7    one file step, h -> a
//   vRank = (h8 - h1) / 7    one rank step, 1 -> 8
//   P(file, rank) = h1 + (7 - fileIdx) * vFile + rankIdx * vRank
// Any kinematic scaling/skew that affects all three corners equally cancels
// out within the board area, so this is robust to bad link lengths or gear
// ratios as long as the board itself is a parallelogram in arm coordinates.
// Z is intentionally NOT part of the calibration — it stays under manual
// control (moveZ / u-j) so the user picks a safe travel height before goto.
static bool  h1Calibrated = false, a1Calibrated = false, h8Calibrated = false;
static float h1X = 0.0f, h1Y = 0.0f;
static float a1X = 0.0f, a1Y = 0.0f;
static float h8X = 0.0f, h8Y = 0.0f;
static bool  trashCalibrated = false;
static float trashX = 0.0f, trashY = 0.0f, trashZ = 0.0f;

static bool boardCalibrated() {
  return h1Calibrated && a1Calibrated && h8Calibrated;
}

static bool fullCalibrated() {
  return boardCalibrated() && trashCalibrated;
}

// (file, rank) -> board (x, y) in mm. file in 'a'..'h', rank in 1..8.
// Returns false if input out of range or board not fully calibrated.
static bool squareToXY(char file, int rank, float& outX, float& outY) {
  if (!boardCalibrated()) return false;
  if (file < 'a' || file > 'h') return false;
  if (rank < 1 || rank > 8)     return false;
  int fileIdx = file - 'a';            // a=0, h=7
  int rankIdx = rank - 1;              // 1=0, 8=7
  float vFileX = (a1X - h1X) / 7.0f;
  float vFileY = (a1Y - h1Y) / 7.0f;
  float vRankX = (h8X - h1X) / 7.0f;
  float vRankY = (h8Y - h1Y) / 7.0f;
  int fileFromH = 7 - fileIdx;         // 0 at h, 7 at a
  outX = h1X + fileFromH * vFileX + rankIdx * vRankX;
  outY = h1Y + fileFromH * vFileY + rankIdx * vRankY;
  return true;
}

static void captureH1() {
  h1X = arm.x(); h1Y = arm.y(); h1Calibrated = true;
  Serial.println("====================================");
  Serial.print("H1 CAPTURED  XY=("); Serial.print(h1X); Serial.print(", ");
  Serial.print(h1Y); Serial.println(")");
  Serial.println("====================================");
}

static void captureA1() {
  a1X = arm.x(); a1Y = arm.y(); a1Calibrated = true;
  Serial.println("====================================");
  Serial.print("A1 CAPTURED  XY=("); Serial.print(a1X); Serial.print(", ");
  Serial.print(a1Y); Serial.println(")");
  Serial.println("====================================");
}

static void captureH8() {
  h8X = arm.x(); h8Y = arm.y(); h8Calibrated = true;
  Serial.println("====================================");
  Serial.print("H8 CAPTURED  XY=("); Serial.print(h8X); Serial.print(", ");
  Serial.print(h8Y); Serial.println(")");
  Serial.println("====================================");
}

static void captureTrash() {
  trashX = arm.x(); trashY = arm.y(); trashZ = arm.z(); trashCalibrated = true;
  Serial.println("====================================");
  Serial.print("TRASH CAPTURED XYZ=("); Serial.print(trashX); Serial.print(", ");
  Serial.print(trashY); Serial.print(", ");
  Serial.print(trashZ); Serial.println(")");
  Serial.println("====================================");
}

static int pieceNameToType(String pieceName) {
  pieceName.toLowerCase();
  if (pieceName == "pawn")   return PAWN;
  if (pieceName == "knight") return KNIGHT;
  if (pieceName == "bishop") return BISHOP;
  if (pieceName == "rook")   return ROOK;
  if (pieceName == "queen")  return QUEEN;
  if (pieceName == "king")   return KING;
  return -1;  // invalid
}

static void printCmHelp() {
  Serial.println("------ controller mode keys ------");
  Serial.println("  w/a/s/d : jog XY (+/- 3 mm)");
  Serial.println("  u/j     : jog Z  (+/- 1.5 mm)");
  Serial.println("  c/v     : close / open gripper");
  Serial.println("  h       : capture current XY as H1");
  Serial.println("  1       : capture current XY as A1");
  Serial.println("  8       : capture current XY as H8");
  Serial.println("  q       : exit controller mode");
  Serial.println("----------------------------------");
}

// Keys that fire immediately while in controller mode (no Enter needed).
// IMPORTANT: any letter listed here cannot appear in a multi-char command while
// cm is ON — it would be consumed before reaching the line buffer. That is why
// `setH1` / `cm` toggle don't work inside cm mode and we expose `h` / `q`
// shortcuts instead.
static bool isJogKey(char c) {
  return c == 'w' || c == 'a' || c == 's' || c == 'd'
      || c == 'u' || c == 'j'
      || c == 'c' || c == 'v'
      || c == 'h' || c == 'q'
      || c == '1' || c == '8';
}

static void handleCommand(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;

  if (cmd.length() == 1) {

    if (controllerMode) {
      if (cmd == "h") { captureH1(); return; }
      if (cmd == "1") { captureA1(); return; }
      if (cmd == "8") { captureH8(); return; }
      if (cmd == "q") {
        controllerMode = false;
        Serial.println("Controller mode OFF");
        return;
      }

      bool moved = true;
      if      (cmd == "w") arm.moveXY(arm.x(), arm.y() + JOG_XY_MM);
      else if (cmd == "s") arm.moveXY(arm.x(), arm.y() - JOG_XY_MM);
      else if (cmd == "a") arm.moveXY(arm.x() - JOG_XY_MM, arm.y());
      else if (cmd == "d") arm.moveXY(arm.x() + JOG_XY_MM, arm.y());
      else if (cmd == "u") arm.moveByZ(JOG_Z_MM);
      else if (cmd == "j") arm.moveByZ(-JOG_Z_MM);
      else if (cmd == "c") { arm.closeGripper(); Serial.println("Gripper: CLOSED"); return; }
      else if (cmd == "v") { arm.openGripper();  Serial.println("Gripper: OPEN");   return; }
      else moved = false;

      if (moved) {
        Serial.print("[cm] pos=(");
        Serial.print(arm.x()); Serial.print(", ");
        Serial.print(arm.y()); Serial.print(", ");
        Serial.print(arm.z()); Serial.println(")");
      }
      return;
    }

    if (cmd == "f") {
      beforeMove();
      xStepper.setDirection(true);
      xStepper.step();
      arm.sync();
      stepCount++;
      afterMove();
    } else if (cmd == "b") {
      beforeMove();
      xStepper.setDirection(false);
      xStepper.step();
      arm.sync();
      stepCount--;
      afterMove();
    } else if (cmd == "w") {
      beforeMove();
      yStepper.setDirection(true);
      yStepper.step();
      arm.sync();
      stepCount++;
      afterMove();
    } else if (cmd == "s") {
      beforeMove();
      yStepper.setDirection(false);
      yStepper.step();
      arm.sync();
      stepCount--;
      afterMove();
    } else if (cmd == "u") {
      beforeMove();
      zStepper.setDirection(true);
      zStepper.step();
      stepCount++;
      afterMove();
    } else if (cmd == "d") {
      beforeMove();
      zStepper.setDirection(false);
      zStepper.step();
      stepCount--;
      afterMove();
    } else if (cmd == "c") {
      arm.closeGripper();
      return;
    } else if (cmd == "v") {
      arm.openGripper();
      return;
    }

    Serial.print("Position: ");
    Serial.print(stepCount);
    Serial.println(" steps");

  } else {
    if (cmd == "OG") {
      arm.openGripper();
    } else if (cmd == "CG") {
      arm.closeGripper();
    } else if (cmd == "GS") {
      Serial.println(arm.gripperOpen() ? "Gripper: open" : "Gripper: closed");
    } else if (cmd == "GA ") {
      float angle = cmd.substring(3).toFloat();
      arm.setGripperAngle(angle);

    } else if (cmd.startsWith("angleX ")) {
      float a = cmd.substring(7).toFloat();
      Serial.println(a);
      arm.moveJ1(a);

    } else if (cmd.startsWith("angleY ")) {
      float a = cmd.substring(7).toFloat();
      arm.moveJ2(a);

    } else if (cmd.startsWith("moveXY ")) {
      String vals = cmd.substring(7);
      int space   = vals.indexOf(' ');
      float x     = vals.substring(0, space).toFloat();
      float y     = vals.substring(space + 1).toFloat();
      Serial.print("Moving to X: "); Serial.print(x);
      Serial.print(", Y: "); Serial.println(y);
      arm.moveXY(x, y);
 
    } else if (cmd.startsWith("moveZ ")) {
      float mm = cmd.substring(6).toFloat();
      Serial.print("Moving Z to: "); Serial.print(mm); Serial.println(" mm");
      arm.moveZ(mm);

    } else if (cmd.startsWith("moveXYZ ")) {
      String vals  = cmd.substring(8);
      int space1   = vals.indexOf(' ');
      int space2   = vals.indexOf(' ', space1 + 1);
      float x = vals.substring(0, space1).toFloat();
      float y = vals.substring(space1 + 1, space2).toFloat();
      float z = vals.substring(space2 + 1).toFloat();
      Serial.print("Moving to X: "); Serial.print(x);
      Serial.print(", Y: "); Serial.print(y);
      Serial.print(", Z: "); Serial.println(z);
      arm.moveXYZ(x, y, z);

    } else if (cmd.startsWith("pick ")) {
      // usage: pick <piece> <square>
      String vals = cmd.substring(5);
      int spaceIdx = vals.indexOf(' ');
      
      if (spaceIdx < 0) {
        Serial.println("usage: pick <piece> <square>, e.g. pick pawn e2");
        Serial.println("pieces: pawn, knight, bishop, rook, queen, king");
        return;
      }
      
      String pieceName = vals.substring(0, spaceIdx);
      String sq = vals.substring(spaceIdx + 1);
      pieceName.trim();
      sq.trim();
      sq.toLowerCase();
      
      int pieceType = pieceNameToType(pieceName);
      if (pieceType < 0) {
        Serial.println("Invalid piece type. Use: pawn, knight, bishop, rook, queen, king");
        return;
      }
      
      if (sq.length() != 2) {
        Serial.println("usage: pick <piece> <square>, e.g. pick pawn e2");
        return;
      }

      char file = sq.charAt(0);
      int rank = sq.charAt(1) - '0';
      float tx, ty;
      if (!squareToXY(file, rank, tx, ty)) {
        if (!boardCalibrated()) {
          Serial.println("Board not fully calibrated. Need all 3 corners:");
          Serial.print("  A1 "); Serial.println(a1Calibrated ? "OK" : "MISSING (cm + 1 or setA1)");
          Serial.print("  H1 "); Serial.println(h1Calibrated ? "OK" : "MISSING (cm + h or setH1)");
          Serial.print("  H8 "); Serial.println(h8Calibrated ? "OK" : "MISSING (cm + 8 or setH8)");
        } else {
          Serial.println("bad square (use a1..h8)");
        }
        return;
      }

      Serial.print("Pick "); Serial.print(pieceName); Serial.print(" from "); Serial.print(sq); Serial.print(" -> XY(");
      Serial.print(tx); Serial.print(", "); Serial.print(ty); Serial.println(")");
      if (!arm.pickAt(tx, ty, pieceType)) Serial.println("Pick failed"); else Serial.println("Pick done");
      return;

    } else if (cmd.startsWith("put ")) {
      // usage: put <piece> <square|trash>
      String vals = cmd.substring(4);
      int spaceIdx = vals.indexOf(' ');
      
      if (spaceIdx < 0) {
        Serial.println("usage: put <piece> <square>, e.g. put queen d1");
        Serial.println("pieces: pawn, knight, bishop, rook, queen, king");
        return;
      }
      
      String pieceName = vals.substring(0, spaceIdx);
      String sq = vals.substring(spaceIdx + 1);
      pieceName.trim();
      sq.trim();
      sq.toLowerCase();

      bool toTrash = (sq == "trash");
      
      int pieceType = pieceNameToType(pieceName);
      if (pieceType < 0) {
        Serial.println("Invalid piece type. Use: pawn, knight, bishop, rook, queen, king");
        return;
      }
      
      float tx, ty;
      if (toTrash) {
        if (!trashCalibrated) {
          Serial.println("Trash not calibrated. Use setTrash first.");
          return;
        }
        tx = trashX;
        ty = trashY;
      } else {
        if (sq.length() != 2) {
          Serial.println("usage: put <piece> <square|trash>, e.g. put queen d1 or put queen trash");
          return;
        }

        char file = sq.charAt(0);
        int rank = sq.charAt(1) - '0';
        if (!squareToXY(file, rank, tx, ty)) {
          if (!boardCalibrated()) {
            Serial.println("Board not fully calibrated. Need all 3 corners:");
            Serial.print("  A1 "); Serial.println(a1Calibrated ? "OK" : "MISSING (cm + 1 or setA1)");
            Serial.print("  H1 "); Serial.println(h1Calibrated ? "OK" : "MISSING (cm + h or setH1)");
            Serial.print("  H8 "); Serial.println(h8Calibrated ? "OK" : "MISSING (cm + 8 or setH8)");
          } else {
            Serial.println("bad square (use a1..h8)");
          }
          return;
        }
      }

      if (toTrash) {
        Serial.print("Put "); Serial.print(pieceName); Serial.print(" to trash -> XYZ(");
        Serial.print(tx); Serial.print(", "); Serial.print(ty); Serial.print(", "); Serial.print(trashZ); Serial.println(")");
        if (!arm.moveXYZ(tx, ty, trashZ)) {
          Serial.println("Put failed");
        } else {
          arm.openGripper();
          Serial.println("Put done");
        }
      } else {
        Serial.print("Put "); Serial.print(pieceName); Serial.print(" to "); Serial.print(sq); Serial.print(" -> XY(");
        Serial.print(tx); Serial.print(", "); Serial.print(ty); Serial.println(")");
        if (!arm.putAt(tx, ty, pieceType)) Serial.println("Put failed"); else Serial.println("Put done");
      }
      return;
    } else if (cmd == "calibrate") {
      arm.calibrate();

    } else if (cmd == "controllerMode" || cmd == "cm") {
      controllerMode = !controllerMode;
      if (controllerMode) {
        Serial.println("Controller mode ON");
        printCmHelp();
      } else {
        Serial.println("Controller mode OFF");
      }
      return;

    } else if (cmd == "setH1") {
      captureH1();
      return;

    } else if (cmd == "setA1") {
      captureA1();
      return;

    } else if (cmd == "setH8") {
      captureH8();
      return;

    } else if (cmd == "setTrash") {
      captureTrash();
      return;

    } else if (cmd == "boardInfo") {
      Serial.print("A1: ");
      if (a1Calibrated) { Serial.print("("); Serial.print(a1X); Serial.print(", "); Serial.print(a1Y); Serial.println(")"); }
      else              { Serial.println("not set"); }
      Serial.print("H1: ");
      if (h1Calibrated) { Serial.print("("); Serial.print(h1X); Serial.print(", "); Serial.print(h1Y); Serial.println(")"); }
      else              { Serial.println("not set"); }
      Serial.print("H8: ");
      if (h8Calibrated) { Serial.print("("); Serial.print(h8X); Serial.print(", "); Serial.print(h8Y); Serial.println(")"); }
      else              { Serial.println("not set"); }
      if (boardCalibrated()) {
        float vFileX = (a1X - h1X) / 7.0f, vFileY = (a1Y - h1Y) / 7.0f;
        float vRankX = (h8X - h1X) / 7.0f, vRankY = (h8Y - h1Y) / 7.0f;
        Serial.print("vFile (h->a, per file): ("); Serial.print(vFileX); Serial.print(", "); Serial.print(vFileY);
        Serial.print(")  |vFile|="); Serial.println(sqrt(vFileX*vFileX + vFileY*vFileY));
        Serial.print("vRank (1->8, per rank): ("); Serial.print(vRankX); Serial.print(", "); Serial.print(vRankY);
        Serial.print(")  |vRank|="); Serial.println(sqrt(vRankX*vRankX + vRankY*vRankY));
      } else {
        Serial.println("(board not fully calibrated)");
      }
      Serial.print("Trash: ");
      if (trashCalibrated) { Serial.print("("); Serial.print(trashX); Serial.print(", "); Serial.print(trashY); Serial.print(", "); Serial.print(trashZ); Serial.println(")"); }
      else                 { Serial.println("not set"); }
      if (!fullCalibrated()) {
        Serial.println("(full calibration not ready: board corners and trash must be set)");
      }
      Serial.print("current Z="); Serial.print(arm.z()); Serial.println(" mm");
      return;

    } else if (cmd.startsWith("goto ")) {
      String sq = cmd.substring(5);
      sq.trim();
      sq.toLowerCase();
      if (sq == "trash") {
        if (!trashCalibrated) {
          Serial.println("Trash not calibrated. Use setTrash first.");
          return;
        }
        Serial.print("[goto trash] ");
        Serial.print("from ("); Serial.print(arm.x()); Serial.print(", "); Serial.print(arm.y());
        Serial.print(") -> ("); Serial.print(trashX); Serial.print(", "); Serial.print(trashY);
        Serial.print(")  Z="); Serial.println(trashZ);
        if (!arm.moveXYZ(trashX, trashY, trashZ)) {
          Serial.println("  FAILED: trash position unreachable from current pose");
        } else {
          Serial.print("  arrived at ("); Serial.print(arm.x()); Serial.print(", ");
          Serial.print(arm.y()); Serial.print(", ");
          Serial.print(arm.z()); Serial.println(")");
        }
        return;
      }
      if (sq.length() != 2) { Serial.println("usage: goto <file><rank>, e.g. goto e4"); return; }
      char file = sq.charAt(0);
      int  rank = sq.charAt(1) - '0';
      float tx, ty;
      if (!squareToXY(file, rank, tx, ty)) {
        if (!boardCalibrated()) {
          Serial.println("Board not fully calibrated. Need all 3 corners:");
          Serial.print("  A1 "); Serial.println(a1Calibrated ? "OK" : "MISSING (cm + 1 or setA1)");
          Serial.print("  H1 "); Serial.println(h1Calibrated ? "OK" : "MISSING (cm + h or setH1)");
          Serial.print("  H8 "); Serial.println(h8Calibrated ? "OK" : "MISSING (cm + 8 or setH8)");
        } else {
          Serial.println("bad square (use a1..h8)");
        }
        return;
      }
      Serial.print("[goto "); Serial.print(sq); Serial.print("] ");
      Serial.print("from ("); Serial.print(arm.x()); Serial.print(", "); Serial.print(arm.y());
      Serial.print(") -> ("); Serial.print(tx); Serial.print(", "); Serial.print(ty);
      Serial.print(")  Z="); Serial.println(arm.z());
      if (!arm.moveXY(tx, ty)) {
        Serial.println("  FAILED: square unreachable from current pose");
      } else {
        Serial.print("  arrived at ("); Serial.print(arm.x()); Serial.print(", ");
        Serial.print(arm.y()); Serial.println(")");
      }
      return;

    } else if (cmd == "pos") {
      Serial.print("Joint1: "); Serial.print(arm.j1Angle()); Serial.println("°");
      Serial.print("Joint2: "); Serial.print(arm.j2Angle()); Serial.println("°");
      Serial.print("Position: (");
      Serial.print(arm.x()); Serial.print(", ");
      Serial.print(arm.y()); Serial.print(", ");
      Serial.print(arm.z()); Serial.println(")");
      return;
    }

    Serial.print("Position: (");
    Serial.print(arm.x()); Serial.print(", ");
    Serial.print(arm.y()); Serial.print(", ");
    Serial.print(arm.z()); Serial.println(")");
    
  }
}
 
void setup() {
  pinMode(ENABLE_PIN, OUTPUT);
  digitalWrite(ENABLE_PIN, LOW);

  Serial.begin(9600);
  arm.begin();
  //Serial1.begin(115200);

  //uiController.begin();
 
  Serial.println("f/b = single step X | w/s = single step Y | u/d = single step Z");
  Serial.println("home | moveXY x y | moveZ z | moveXYZ x y z | pos");
  Serial.println("OG/CG = open/close gripper | v/c = open/close gripper | GS = gripper status");
  Serial.println("cm = enter controller mode (w/a/s/d=XY, u/j=Z, c/v=gripper, h/1/8=setH1/A1/H8, q=exit)");
  Serial.println("setA1 / setH1 / setH8 / setTrash = capture corners/trash | goto <sq|trash> e.g. goto e4 | boardInfo");
  Serial.println("pick <sq> | put <sq> | put <piece> trash (trash uses calibrated XYZ)");
  Serial.println("pick <piece> <sq> | put <piece> <sq> (pieces: pawn, knight, bishop, rook, queen, king)");
}
 
void loop() {
  updateDrivers();
  
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;

    // In controller mode, jog keys dispatch immediately (no Enter needed) so
    // that holding the key auto-repeats into continuous motion. Multi-char
    // commands like `cm` still work because their letters aren't jog keys.
    if (controllerMode && isJogKey(c)) {
      handleCommand(String(c));
      continue;
    }

    if (c == '\n') {
      handleCommand(cmdBuffer);
      cmdBuffer = "";
    } else {
      cmdBuffer += c;
    }
  }

  //uiController.loop();
}