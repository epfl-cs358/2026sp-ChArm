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

// Chess board calibration.
// Board orientation is mechanically fixed: edge along y=0 is parallel to the
// black-pawn row (arm sits on white side), edge along x=0 is the A-column side.
// So A is at small x, H at large x, rank 1 at small y, rank 8 at large y.
// User jogs to H1 with WASD and runs `setH1`; every other square is derived.
// Z is intentionally NOT part of the calibration — it stays under manual control
// (use moveZ / u-j in cm mode) so the user is responsible for being at a safe
// travel height before each `goto`.
static const float SQUARE_MM = 37.5f;  // 3.75 cm per square
static bool  h1Calibrated = false;
static float h1X = 0.0f, h1Y = 0.0f;

// (file, rank) -> board (x, y) in mm. file in 'a'..'h', rank in 1..8.
// Returns false if input out of range or H1 not yet calibrated.
static bool squareToXY(char file, int rank, float& outX, float& outY) {
  if (!h1Calibrated) return false;
  if (file < 'a' || file > 'h') return false;
  if (rank < 1 || rank > 8)     return false;
  int fileIdx = file - 'a';            // a=0, h=7
  int rankIdx = rank - 1;              // 1=0, 8=7
  outX = h1X - (7 - fileIdx) * SQUARE_MM;
  outY = h1Y + rankIdx * SQUARE_MM;
  return true;
}

static void captureH1() {
  h1X = arm.x();
  h1Y = arm.y();
  h1Calibrated = true;
  Serial.println("====================================");
  Serial.println("H1 CAPTURED");
  Serial.print("  XY = ("); Serial.print(h1X); Serial.print(", ");
  Serial.print(h1Y); Serial.println(")");
  Serial.print("  current Z = "); Serial.print(arm.z()); Serial.println(" mm (not stored)");
  Serial.println("  Z stays under manual control (moveZ / u-j keys).");
  Serial.println("====================================");
}

static void printCmHelp() {
  Serial.println("------ controller mode keys ------");
  Serial.println("  w/a/s/d : jog XY (+/- 3 mm)");
  Serial.println("  u/j     : jog Z  (+/- 1.5 mm)");
  Serial.println("  c/v     : close / open gripper");
  Serial.println("  h       : capture current XY as H1");
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
      || c == 'h' || c == 'q';
}

static void handleCommand(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;

  if (cmd.length() == 1) {

    if (controllerMode) {
      if (cmd == "h") { captureH1(); return; }
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
      xStepper.setDirection(true);
      xStepper.step();
      arm.sync();
      stepCount++;
    } else if (cmd == "b") {
      xStepper.setDirection(false);
      xStepper.step();
      arm.sync();
      stepCount--;
    } else if (cmd == "w") {
      yStepper.setDirection(true);
      yStepper.step();
      arm.sync();
      stepCount++;
    } else if (cmd == "s") {
      yStepper.setDirection(false);
      yStepper.step();
      arm.sync();
      stepCount--;
    } else if (cmd == "u") {
      zStepper.setDirection(true);
      zStepper.step();
      stepCount++;
    } else if (cmd == "d") {
      zStepper.setDirection(false);
      zStepper.step();
      stepCount--;
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

    } else if (cmd == "boardInfo") {
      if (!h1Calibrated) { Serial.println("H1 not calibrated. Jog to H1 then run setH1."); return; }
      Serial.print("H1 XY=("); Serial.print(h1X); Serial.print(", ");
      Serial.print(h1Y); Serial.println(")");
      Serial.print("square="); Serial.print(SQUARE_MM); Serial.println(" mm");
      Serial.print("current Z="); Serial.print(arm.z()); Serial.println(" mm");
      return;

    } else if (cmd.startsWith("goto ")) {
      String sq = cmd.substring(5);
      sq.trim();
      sq.toLowerCase();
      if (sq.length() != 2) { Serial.println("usage: goto <file><rank>, e.g. goto e4"); return; }
      char file = sq.charAt(0);
      int  rank = sq.charAt(1) - '0';
      float tx, ty;
      if (!squareToXY(file, rank, tx, ty)) {
        if (!h1Calibrated) Serial.println("H1 not calibrated. Jog to H1 then run setH1 (or press h in cm).");
        else               Serial.println("bad square (use a1..h8)");
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
  Serial.println("cm = enter controller mode (w/a/s/d=XY, u/j=Z, c/v=gripper, h=setH1, q=exit)");
  Serial.println("setH1 = capture current XY as H1 | goto <sq> e.g. goto e4 | boardInfo");
}
 
void loop() {
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