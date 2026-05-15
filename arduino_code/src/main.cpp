#include <Arduino.h>
#include <EEPROM.h>
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
ScaraJoint joint2(yStepper, STEPS_PER_REV, MICROSTEPS, GEAR_RATIO_J2, j2Lim, true);  //forearm
Gripper gripper(GRIPPER_PIN, OPEN_ANGLE, CLOSED_ANGLE);
LeadScrew leadScrew(zStepper, STEPS_PER_MM, Z_MAX_MM, zLim);

ScaraArm arm(joint1, joint2, leadScrew, gripper, LINK1_LENGTH, LINK2_LENGTH);

UIState uiState;
ButtonInput buttonInput(CLK_PIN, DT_PIN, SW_PIN);
LCDDisplay lcd(RS_PIN, E_PIN, D4_PIN, D5_PIN, D6_PIN, D7_PIN);
UIController uiController(buttonInput, uiState, lcd, Serial1);

int stepCount = 0;
static String cmdBuffer = "";
static String esp32CamIP = "";
static String serial1Buf  = "";
static const unsigned long ESP32_REPLY_TIMEOUT_MS = 2000;

// Cartesian jog mode: w/a/s/d move XY, u/j move Z. Toggle with `cm`.
static bool controllerMode  = false;
static bool calibrationMode = false;
static const float JOG_XY_MM     = 3.0f;
static const float JOG_Z_MM      = 1.5f;
static const float CAL_JOG_XY_MM = 1.0f;
static const float CAL_JOG_Z_MM  = 0.5f;

// ── Board calibration ────────────────────────────────────────────────────────
// 3-corner vector decomposition: capture arm (x,y) at H1, A1, H8.
// Every square is then: P = h1 + fileFromH*vFile + rankIdx*vRank
// Z is NOT part of board calibration — user picks travel height manually.
static bool  h1Calibrated = false, a1Calibrated = false, h8Calibrated = false;
static float h1X = 0, h1Y = 0;
static float a1X = 0, a1Y = 0;
static float h8X = 0, h8Y = 0;
static bool  trashCalibrated = false;
static float trashX = 0, trashY = 0;

static bool boardCalibrated() { return h1Calibrated && a1Calibrated && h8Calibrated; }
static bool fullCalibrated()  { return boardCalibrated() && trashCalibrated; }

// ── EEPROM persistence ───────────────────────────────────────────────────────
// Layout: [0..3] magic "CALB" | [4..35] eight floats h1X,h1Y,a1X,a1Y,h8X,h8Y,trashX,trashY | [36] XOR checksum
static const int     EEPROM_CAL_ADDR = 0;
static const uint8_t CAL_MAGIC[4]    = { 'C', 'A', 'L', 'B' };
static const int     EEPROM_CAL_LEN  = 37;

static bool loadCalFromEEPROM() {
  for (int i = 0; i < 4; i++)
    if (EEPROM.read(EEPROM_CAL_ADDR + i) != CAL_MAGIC[i]) return false;
  uint8_t cs = 0;
  for (int i = 0; i < EEPROM_CAL_LEN - 1; i++) cs ^= EEPROM.read(EEPROM_CAL_ADDR + i);
  if (cs != EEPROM.read(EEPROM_CAL_ADDR + EEPROM_CAL_LEN - 1)) return false;
  float buf[8];
  for (int i = 0; i < 8; i++) EEPROM.get(EEPROM_CAL_ADDR + 4 + i * 4, buf[i]);
  h1X = buf[0]; h1Y = buf[1];
  a1X = buf[2]; a1Y = buf[3];
  h8X = buf[4]; h8Y = buf[5];
  trashX = buf[6]; trashY = buf[7];
  h1Calibrated = a1Calibrated = h8Calibrated = trashCalibrated = true;
  return true;
}

static void saveCalToEEPROM() {
  for (int i = 0; i < 4; i++) EEPROM.update(EEPROM_CAL_ADDR + i, CAL_MAGIC[i]);
  EEPROM.put(EEPROM_CAL_ADDR + 4,  h1X);
  EEPROM.put(EEPROM_CAL_ADDR + 8,  h1Y);
  EEPROM.put(EEPROM_CAL_ADDR + 12, a1X);
  EEPROM.put(EEPROM_CAL_ADDR + 16, a1Y);
  EEPROM.put(EEPROM_CAL_ADDR + 20, h8X);
  EEPROM.put(EEPROM_CAL_ADDR + 24, h8Y);
  EEPROM.put(EEPROM_CAL_ADDR + 28, trashX);
  EEPROM.put(EEPROM_CAL_ADDR + 32, trashY);
  uint8_t cs = 0;
  for (int i = 0; i < EEPROM_CAL_LEN - 1; i++) cs ^= EEPROM.read(EEPROM_CAL_ADDR + i);
  EEPROM.update(EEPROM_CAL_ADDR + EEPROM_CAL_LEN - 1, cs);
}

static void clearCalEEPROM() {
  for (int i = 0; i < EEPROM_CAL_LEN; i++) EEPROM.update(EEPROM_CAL_ADDR + i, 0xFF);
}

// ── Calibration wizard ───────────────────────────────────────────────────────
// Walks user through H1 -> A1 -> H8 -> Trash. 'v' locks, 'n' skips,
// 'p' goes back, 'q' cancels and reverts. Saves to EEPROM when all 4 done.
enum CalStep : uint8_t { CAL_H1 = 0, CAL_A1 = 1, CAL_H8 = 2, CAL_TRASH = 3 };
static CalStep calStep = CAL_H1;

// Snapshot: saved on entering cal mode, restored on cancel
static bool  snapH1c, snapA1c, snapH8c, snapTrashc;
static float snapH1X, snapH1Y, snapA1X, snapA1Y, snapH8X, snapH8Y;
static float snapTrashX, snapTrashY;

static const char* calCornerName(CalStep s) {
  if (s == CAL_H1)    return "H1";
  if (s == CAL_A1)    return "A1";
  if (s == CAL_H8)    return "H8";
  return "Trash";
}

static bool calCornerSaved(CalStep s) {
  if (s == CAL_H1)    return h1Calibrated;
  if (s == CAL_A1)    return a1Calibrated;
  if (s == CAL_H8)    return h8Calibrated;
  return trashCalibrated;
}

static void calGetSavedXY(CalStep s, float& x, float& y) {
  if (s == CAL_H1)       { x = h1X;    y = h1Y; }
  else if (s == CAL_A1)  { x = a1X;    y = a1Y; }
  else if (s == CAL_H8)  { x = h8X;    y = h8Y; }
  else                   { x = trashX; y = trashY; }
}

static void captureCalCorner(CalStep s) {
  if (s == CAL_H1)       { h1X = arm.x(); h1Y = arm.y(); h1Calibrated = true; }
  else if (s == CAL_A1)  { a1X = arm.x(); a1Y = arm.y(); a1Calibrated = true; }
  else if (s == CAL_H8)  { h8X = arm.x(); h8Y = arm.y(); h8Calibrated = true; }
  else { trashX = arm.x(); trashY = arm.y(); trashCalibrated = true; }
  Serial.print("[cal] "); Serial.print(calCornerName(s));
  Serial.print(" set to ("); Serial.print(arm.x()); Serial.print(", "); Serial.print(arm.y());
  Serial.println(")");
}

static void snapshotCal() {
  snapH1c = h1Calibrated; snapH1X = h1X; snapH1Y = h1Y;
  snapA1c = a1Calibrated; snapA1X = a1X; snapA1Y = a1Y;
  snapH8c = h8Calibrated; snapH8X = h8X; snapH8Y = h8Y;
  snapTrashc = trashCalibrated; snapTrashX = trashX; snapTrashY = trashY;
}

static void restoreCalSnapshot() {
  h1Calibrated = snapH1c; h1X = snapH1X; h1Y = snapH1Y;
  a1Calibrated = snapA1c; a1X = snapA1X; a1Y = snapA1Y;
  h8Calibrated = snapH8c; h8X = snapH8X; h8Y = snapH8Y;
  trashCalibrated = snapTrashc; trashX = snapTrashX; trashY = snapTrashY;
}

static void promptCalStep(CalStep s) {
  Serial.println("====================================");
  Serial.print("[cal] Step "); Serial.print((int)s + 1); Serial.print("/4: ");
  Serial.println(calCornerName(s));
  if (s == CAL_TRASH)
    Serial.println("  Move arm to trash position (XY only — Z is hardcoded in config).");
  if (calCornerSaved(s)) {
    float tx, ty; calGetSavedXY(s, tx, ty);
    Serial.print("  saved=("); Serial.print(tx); Serial.print(", "); Serial.print(ty);
    Serial.println(") — moving there. Nudge to fine-tune.");
    if (!arm.moveXY(tx, ty))
      Serial.println("  WARNING: saved position unreachable. Jog manually.");
  } else {
    Serial.println("  no saved value — move arm here manually.");
  }
  Serial.println("  wasd/uj=jog  v=validate  n=skip  p=prev  q=cancel");
  Serial.println("====================================");
}

static void enterCalModeAt(CalStep startStep) {
  if (calibrationMode) return;
  calibrationMode = true;
  snapshotCal();
  calStep = startStep;
  Serial.println("Calibration mode ON");
  Serial.print("  H1:    "); Serial.println(h1Calibrated    ? "saved" : "MISSING");
  Serial.print("  A1:    "); Serial.println(a1Calibrated    ? "saved" : "MISSING");
  Serial.print("  H8:    "); Serial.println(h8Calibrated    ? "saved" : "MISSING");
  Serial.print("  Trash: "); Serial.println(trashCalibrated ? "saved" : "MISSING");
  promptCalStep(calStep);
}

static void enterCalMode() {
  enterCalModeAt(CAL_H1);
}

static void finishCalMode() {
  calibrationMode = false;
  if (fullCalibrated()) {
    saveCalToEEPROM();
    Serial.println("[cal] All 4 points set. Saved to EEPROM.");
  } else {
    Serial.println("[cal] Incomplete — not all points set. EEPROM unchanged.");
    Serial.print("  H1    "); Serial.println(h1Calibrated    ? "OK" : "MISSING");
    Serial.print("  A1    "); Serial.println(a1Calibrated    ? "OK" : "MISSING");
    Serial.print("  H8    "); Serial.println(h8Calibrated    ? "OK" : "MISSING");
    Serial.print("  Trash "); Serial.println(trashCalibrated ? "OK" : "MISSING");
  }
}

static void cancelCalMode() {
  calibrationMode = false;
  restoreCalSnapshot();
  Serial.println("[cal] Cancelled. Reverted to prior values.");
}

// ── Square → XY ─────────────────────────────────────────────────────────────
static bool squareToXY(char file, int rank, float& outX, float& outY) {
  if (!boardCalibrated()) return false;
  if (file < 'a' || file > 'h') return false;
  if (rank < 1   || rank > 8)   return false;
  int fileIdx   = file - 'a';
  int rankIdx   = rank - 1;
  float vFileX  = (a1X - h1X) / 7.0f, vFileY = (a1Y - h1Y) / 7.0f;
  float vRankX  = (h8X - h1X) / 7.0f, vRankY = (h8Y - h1Y) / 7.0f;
  int fileFromH = 7 - fileIdx;
  outX = h1X + fileFromH * vFileX + rankIdx * vRankX;
  outY = h1Y + fileFromH * vFileY + rankIdx * vRankY;
  return true;
}

// ── Capture helpers (direct commands, outside wizard) ───────────────────────
static void captureH1() {
  h1X = arm.x(); h1Y = arm.y(); h1Calibrated = true;
  Serial.println("====================================");
  Serial.print("H1 CAPTURED  XY=("); Serial.print(h1X); Serial.print(", "); Serial.print(h1Y); Serial.println(")");
  Serial.println("====================================");
}
static void captureA1() {
  a1X = arm.x(); a1Y = arm.y(); a1Calibrated = true;
  Serial.println("====================================");
  Serial.print("A1 CAPTURED  XY=("); Serial.print(a1X); Serial.print(", "); Serial.print(a1Y); Serial.println(")");
  Serial.println("====================================");
}
static void captureH8() {
  h8X = arm.x(); h8Y = arm.y(); h8Calibrated = true;
  Serial.println("====================================");
  Serial.print("H8 CAPTURED  XY=("); Serial.print(h8X); Serial.print(", "); Serial.print(h8Y); Serial.println(")");
  Serial.println("====================================");
}
static void captureTrash() {
  trashX = arm.x(); trashY = arm.y(); trashCalibrated = true;
  Serial.println("====================================");
  Serial.print("TRASH CAPTURED XY=("); Serial.print(trashX); Serial.print(", ");
  Serial.print(trashY); Serial.println(")");
  Serial.println("====================================");
}

// ── Piece helpers ────────────────────────────────────────────────────────────
static int pieceNameToType(String pieceName) {
  pieceName.toLowerCase();
  if (pieceName == "pawn")   return PAWN;
  if (pieceName == "knight") return KNIGHT;
  if (pieceName == "bishop") return BISHOP;
  if (pieceName == "rook")   return ROOK;
  if (pieceName == "queen")  return QUEEN;
  if (pieceName == "king")   return KING;
  return -1;
}

// ── Key classification ───────────────────────────────────────────────────────
static bool isCmKey(char c) {
  return c == 'w' || c == 'a' || c == 's' || c == 'd'
      || c == 'u' || c == 'j'
      || c == 'c' || c == 'v'
      || c == 'q';
}

static bool isCalKey(char c) {
  return c == 'w' || c == 'a' || c == 's' || c == 'd'
      || c == 'u' || c == 'j'
      || c == 'v' || c == 'n' || c == 'p' || c == 'q';
}

// ── Help ─────────────────────────────────────────────────────────────────────
static void printCmHelp() {
  Serial.println("------ controller mode keys ------");
  Serial.println("  w/a/s/d : jog XY (+/- 3 mm)");
  Serial.println("  u/j     : jog Z  (+/- 1.5 mm)");
  Serial.println("  c/v     : close / open gripper");
  Serial.println("  q       : exit controller mode");
  Serial.println("----------------------------------");
}

static bool updateEsp32CamIPFromLine(String line) {
  line.trim();

  if (line.startsWith("WIFI_OK ")) {
    esp32CamIP = line.substring(8);
    esp32CamIP.trim();
    return esp32CamIP.length() > 0;
  }

  if (line.startsWith("IP ")) {
    esp32CamIP = line.substring(3);
    esp32CamIP.trim();
    return esp32CamIP.length() > 0;
  }

  return false;
}

static bool readEsp32Line(String &line, unsigned long timeoutMs) {
  line = "";
  unsigned long deadline = millis() + timeoutMs;

  while (millis() < deadline) {
    if (Serial2.available()) {
      char c = (char)Serial2.read();
      if (c == '\r') continue;
      if (c == '\n') {
        line.trim();
        return line.length() > 0;
      }
      line += c;
    }
  }

  line.trim();
  return line.length() > 0;
}

static bool refreshEsp32CamIP() {
  while (Serial2.available()) Serial2.read();
  Serial2.println("IP");

  String reply = "";
  if (!readEsp32Line(reply, ESP32_REPLY_TIMEOUT_MS)) {
    return false;
  }

  return updateEsp32CamIPFromLine(reply);
}

// ── Command handler ───────────────────────────────────────────────────────────
static void handleCommand(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;

  if (cmd.length() == 1) {

    // ── Calibration wizard keys ──────────────────────────────────────────────
    if (calibrationMode) {
      if (cmd == "q") { cancelCalMode(); return; }

      if (cmd == "v") {
        captureCalCorner(calStep);
        if (calStep == CAL_TRASH) { finishCalMode(); return; }
        calStep = (CalStep)(calStep + 1);
        promptCalStep(calStep);
        return;
      }
      if (cmd == "n") {
        if (calStep == CAL_TRASH) { finishCalMode(); return; }
        calStep = (CalStep)(calStep + 1);
        promptCalStep(calStep);
        return;
      }
      if (cmd == "p") {
        if (calStep == CAL_H1) { Serial.println("[cal] already at first corner"); return; }
        calStep = (CalStep)(calStep - 1);
        promptCalStep(calStep);
        return;
      }

      bool moved = true;
      if      (cmd == "w") arm.moveXY(arm.x(), arm.y() + CAL_JOG_XY_MM);
      else if (cmd == "s") arm.moveXY(arm.x(), arm.y() - CAL_JOG_XY_MM);
      else if (cmd == "a") arm.moveXY(arm.x() - CAL_JOG_XY_MM, arm.y());
      else if (cmd == "d") arm.moveXY(arm.x() + CAL_JOG_XY_MM, arm.y());
      else if (cmd == "u") arm.moveByZ( CAL_JOG_Z_MM);
      else if (cmd == "j") arm.moveByZ(-CAL_JOG_Z_MM);
      else moved = false;

      if (moved) {
        Serial.print("[cal "); Serial.print(calCornerName(calStep)); Serial.print("] pos=(");
        Serial.print(arm.x()); Serial.print(", ");
        Serial.print(arm.y()); Serial.print(", ");
        Serial.print(arm.z()); Serial.println(")");
      }
      return;
    }

    // ── Controller mode keys ─────────────────────────────────────────────────
    if (controllerMode) {
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
      else if (cmd == "u") arm.moveByZ( JOG_Z_MM);
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

    // ── Raw step jog ─────────────────────────────────────────────────────────
    if (cmd == "f") {
      beforeMove();
      xStepper.setDirection(true); xStepper.step(); arm.sync(); stepCount++;
      afterMove();
    } else if (cmd == "b") {
      beforeMove();
      xStepper.setDirection(false); xStepper.step(); arm.sync(); stepCount--;
      afterMove();
    } else if (cmd == "w") {
      beforeMove();
      yStepper.setDirection(true); yStepper.step(); arm.sync(); stepCount++;
      afterMove();
    } else if (cmd == "s") {
      beforeMove();
      yStepper.setDirection(false); yStepper.step(); arm.sync(); stepCount--;
      afterMove();
    } else if (cmd == "u") {
      beforeMove();
      zStepper.setDirection(true); zStepper.step(); stepCount++;
      afterMove();
    } else if (cmd == "d") {
      beforeMove();
      zStepper.setDirection(false); zStepper.step(); stepCount--;
      afterMove();
    } else if (cmd == "c") {
      arm.closeGripper(); return;
    } else if (cmd == "v") {
      arm.openGripper(); return;
    }

    Serial.print("Position: "); Serial.print(stepCount); Serial.println(" steps");

  } else {

    // ── Multi-char commands ───────────────────────────────────────────────────
    if (cmd == "OG") {
      arm.openGripper();
    } else if (cmd == "CG") {
      arm.closeGripper();
    } else if (cmd == "GS") {
      Serial.println(arm.gripperOpen() ? "Gripper: open" : "Gripper: closed");

    } else if (cmd.startsWith("GA ")) {
      arm.setGripperAngle(cmd.substring(3).toFloat());

    } else if (cmd.startsWith("angleX ")) {
      arm.moveJ1(cmd.substring(7).toFloat());

    } else if (cmd.startsWith("angleY ")) {
      arm.moveJ2(cmd.substring(7).toFloat());

    } else if (cmd.startsWith("moveXY ")) {
      String vals = cmd.substring(7);
      int sp = vals.indexOf(' ');
      float x = vals.substring(0, sp).toFloat();
      float y = vals.substring(sp + 1).toFloat();
      Serial.print("Moving to X: "); Serial.print(x); Serial.print(", Y: "); Serial.println(y);
      arm.moveXY(x, y);

    } else if (cmd.startsWith("moveZ ")) {
      float mm = cmd.substring(6).toFloat();
      Serial.print("Moving Z to: "); Serial.print(mm); Serial.println(" mm");
      arm.moveZ(mm);

    } else if (cmd.startsWith("moveXYZ ")) {
      String vals = cmd.substring(8);
      int sp1 = vals.indexOf(' ');
      int sp2 = vals.indexOf(' ', sp1 + 1);
      float x = vals.substring(0, sp1).toFloat();
      float y = vals.substring(sp1 + 1, sp2).toFloat();
      float z = vals.substring(sp2 + 1).toFloat();
      Serial.print("Moving to X: "); Serial.print(x);
      Serial.print(", Y: "); Serial.print(y);
      Serial.print(", Z: "); Serial.println(z);
      arm.moveXYZ(x, y, z);

    } else if (cmd == "home") {
      Serial.println("Going home: J1=0, J2=0, Z=hover");
      arm.goHome();

    } else if (cmd.startsWith("pick ")) {
      String vals = cmd.substring(5);
      int sp = vals.indexOf(' ');
      if (sp < 0) { Serial.println("usage: pick <piece> <square>"); return; }
      String pieceName = vals.substring(0, sp);
      String sq = vals.substring(sp + 1);
      pieceName.trim(); sq.trim(); sq.toLowerCase();
      int pieceType = pieceNameToType(pieceName);
      if (pieceType < 0) { Serial.println("Invalid piece. Use: pawn, knight, bishop, rook, queen, king"); return; }
      if (sq.length() != 2) { Serial.println("usage: pick <piece> <square>, e.g. pick pawn e2"); return; }
      char file = sq.charAt(0);
      int  rank = sq.charAt(1) - '0';
      float tx, ty;
      if (!squareToXY(file, rank, tx, ty)) {
        Serial.println(boardCalibrated() ? "bad square (use a1..h8)" : "Board not fully calibrated. Run `cal`.");
        return;
      }
      Serial.print("Pick "); Serial.print(pieceName); Serial.print(" from "); Serial.print(sq);
      Serial.print(" -> XY("); Serial.print(tx); Serial.print(", "); Serial.print(ty); Serial.println(")");
      if (!arm.pickAt(tx, ty, pieceType)) Serial.println("Pick failed"); else Serial.println("Pick done");

    } else if (cmd.startsWith("put ")) {
      String vals = cmd.substring(4);
      int sp = vals.indexOf(' ');
      if (sp < 0) { Serial.println("usage: put <piece> <square|trash>"); return; }
      String pieceName = vals.substring(0, sp);
      String sq = vals.substring(sp + 1);
      pieceName.trim(); sq.trim(); sq.toLowerCase();
      bool toTrash = (sq == "trash");
      int pieceType = pieceNameToType(pieceName);
      if (pieceType < 0) { Serial.println("Invalid piece. Use: pawn, knight, bishop, rook, queen, king"); return; }
      float tx, ty;
      if (toTrash) {
        if (!trashCalibrated) { Serial.println("Trash not calibrated. Use setTrash first."); return; }
        tx = trashX; ty = trashY; // Note: trashZ is hardcoded in config
      } else {
        if (sq.length() != 2) { Serial.println("usage: put <piece> <square|trash>"); return; }
        char file = sq.charAt(0);
        int  rank = sq.charAt(1) - '0';
        if (!squareToXY(file, rank, tx, ty)) {
          Serial.println(boardCalibrated() ? "bad square (use a1..h8)" : "Board not fully calibrated. Run `cal`.");
          return;
        }
      }
      if (toTrash) {
        Serial.print("Put "); Serial.print(pieceName); Serial.print(" to trash -> XYZ(");
        Serial.print(tx); Serial.print(", "); Serial.print(ty); Serial.print(", "); Serial.print(TRASH_Z); Serial.println(")");
        if (!arm.moveXYZ(tx, ty, TRASH_Z)) Serial.println("Put failed");
        else { arm.openGripper(); Serial.println("Put done"); }
      } else {
        Serial.print("Put "); Serial.print(pieceName); Serial.print(" to "); Serial.print(sq);
        Serial.print(" -> XY("); Serial.print(tx); Serial.print(", "); Serial.print(ty); Serial.println(")");
        if (!arm.putAt(tx, ty, pieceType)) Serial.println("Put failed"); else Serial.println("Put done");
      }

    } else if (cmd == "calibrate") {
      arm.calibrate();

    } else if (cmd == "controllerMode" || cmd == "cm") {
      if (calibrationMode) { Serial.println("Exit calibration first (q)."); return; }
      controllerMode = !controllerMode;
      if (controllerMode) { Serial.println("Controller mode ON"); printCmHelp(); }
      else                { Serial.println("Controller mode OFF"); }
      return;

    } else if (cmd.startsWith("injectCal ")) {
      // injectCal <h1x> <h1y> <a1x> <a1y> <h8x> <h8y> <trashx> <trashy>
      String vals = cmd.substring(10);
      float buf[8];
      int pos = 0;
      for (int i = 0; i < 8; i++) {
        int sp = vals.indexOf(' ', pos);
        String token = (sp < 0) ? vals.substring(pos) : vals.substring(pos, sp);
        buf[i] = token.toFloat();
        pos = sp + 1;
        if (sp < 0 && i < 7) { Serial.println("injectCal ERR: expected 8 values"); return; }
      }
      h1X = buf[0]; h1Y = buf[1];
      a1X = buf[2]; a1Y = buf[3];
      h8X = buf[4]; h8Y = buf[5];
      trashX = buf[6]; trashY = buf[7];
      h1Calibrated = h8Calibrated = a1Calibrated = trashCalibrated = true;
      saveCalToEEPROM();
      Serial.print("CAL_INJECTED H1=("); Serial.print(h1X); Serial.print(","); Serial.print(h1Y);
      Serial.print(") A1=("); Serial.print(a1X); Serial.print(","); Serial.print(a1Y);
      Serial.print(") H8=("); Serial.print(h8X); Serial.print(","); Serial.print(h8Y);
      Serial.print(") Trash=("); Serial.print(trashX); Serial.print(","); Serial.print(trashY); Serial.println(")");
      return;

    } else if (cmd == "cal" || cmd == "boardCal") {
      if (controllerMode) { Serial.println("Exit controller mode first (q)."); return; }
      enterCalMode();
      return;

    } else if (cmd == "calTrash" || cmd == "trashCal") {
      if (controllerMode) { Serial.println("Exit controller mode first (q)."); return; }
      if (!boardCalibrated()) { Serial.println("Board points missing. Run `cal` first."); return; }
      // Force manual/jog flow for trash by ignoring old saved trash point.
      trashCalibrated = false;
      enterCalModeAt(CAL_TRASH);
      return;

    } else if (cmd == "calClear") {
      clearCalEEPROM();
      h1Calibrated = a1Calibrated = h8Calibrated = trashCalibrated = false;
      Serial.println("EEPROM calibration cleared.");
      return;

    } else if (cmd == "setH1") {
      captureH1(); return;
    } else if (cmd == "setA1") {
      captureA1(); return;
    } else if (cmd == "setH8") {
      captureH8(); return;
    } else if (cmd == "setTrash") {
      captureTrash(); return;

    } else if (cmd == "boardInfo") {
      Serial.print("A1: ");
      if (a1Calibrated) { Serial.print("("); Serial.print(a1X); Serial.print(", "); Serial.print(a1Y); Serial.println(")"); }
      else Serial.println("not set");
      Serial.print("H1: ");
      if (h1Calibrated) { Serial.print("("); Serial.print(h1X); Serial.print(", "); Serial.print(h1Y); Serial.println(")"); }
      else Serial.println("not set");
      Serial.print("H8: ");
      if (h8Calibrated) { Serial.print("("); Serial.print(h8X); Serial.print(", "); Serial.print(h8Y); Serial.println(")"); }
      else Serial.println("not set");
      if (boardCalibrated()) {
        float vFileX = (a1X - h1X) / 7.0f, vFileY = (a1Y - h1Y) / 7.0f;
        float vRankX = (h8X - h1X) / 7.0f, vRankY = (h8Y - h1Y) / 7.0f;
        Serial.print("vFile: ("); Serial.print(vFileX); Serial.print(", "); Serial.print(vFileY);
        Serial.print(")  |vFile|="); Serial.println(sqrt(vFileX*vFileX + vFileY*vFileY));
        Serial.print("vRank: ("); Serial.print(vRankX); Serial.print(", "); Serial.print(vRankY);
        Serial.print(")  |vRank|="); Serial.println(sqrt(vRankX*vRankX + vRankY*vRankY));
      } else {
        Serial.println("(board not fully calibrated)");
      }
      Serial.print("Trash: ");
      if (trashCalibrated) { Serial.print("("); Serial.print(trashX); Serial.print(", "); Serial.print(trashY); Serial.println(")"); }
      else Serial.println("not set");
      if (!fullCalibrated()) Serial.println("(full calibration not ready)");
      Serial.print("current Z="); Serial.print(arm.z()); Serial.println(" mm");
      return;

    } else if (cmd.startsWith("driver")) {
      Serial.println(driversEnabled() ? "Drivers: ON" : "Drivers: OFF");
      return;

    } else if (cmd.startsWith("goto ")) {
      String sq = cmd.substring(5);
      sq.trim(); sq.toLowerCase();
      if (sq == "trash") {
        if (!trashCalibrated) { Serial.println("Trash not calibrated. Use setTrash first."); return; }
        Serial.print("[goto trash] -> ("); Serial.print(trashX); Serial.print(", "); Serial.print(trashY); Serial.print(", "); Serial.print(TRASH_Z); Serial.println(")");
        if (!arm.moveXYZ(trashX, trashY, TRASH_Z)) Serial.println("  FAILED: trash position unreachable");
        else { Serial.print("  arrived at ("); Serial.print(arm.x()); Serial.print(", "); Serial.print(arm.y()); Serial.print(", "); Serial.print(arm.z()); Serial.println(")"); }
        return;
      }
      if (sq.length() != 2) { Serial.println("usage: goto <file><rank>, e.g. goto e4"); return; }
      char file = sq.charAt(0);
      int  rank = sq.charAt(1) - '0';
      float tx, ty;
      if (!squareToXY(file, rank, tx, ty)) {
        Serial.println(boardCalibrated() ? "bad square (use a1..h8)" : "Board not fully calibrated. Run `cal`.");
        return;
      }
      Serial.print("[goto "); Serial.print(sq); Serial.print("] -> ("); Serial.print(tx); Serial.print(", "); Serial.print(ty); Serial.println(")");
      if (!arm.moveXY(tx, ty)) Serial.println("  FAILED: square unreachable");
      else { Serial.print("  arrived at ("); Serial.print(arm.x()); Serial.print(", "); Serial.print(arm.y()); Serial.println(")"); }
      return;

    } else if (cmd == "esp32status") {
      Serial.print("Cached IP: ");
      Serial.println(esp32CamIP.length() > 0 ? esp32CamIP : "(none)");
      String reply = "";
      while (Serial2.available()) Serial2.read();
      Serial2.println("IP");
      readEsp32Line(reply, ESP32_REPLY_TIMEOUT_MS);
      updateEsp32CamIPFromLine(reply);
      Serial.print("ESP32 reply: ");
      Serial.println(reply.length() > 0 ? reply : "(no response - check Serial2 wiring on Mega pins 16/17)");
      Serial.print("Resolved IP: ");
      Serial.println(esp32CamIP.length() > 0 ? esp32CamIP : "(none)");
      return;

    } else if (cmd == "photo") {
      if (esp32CamIP.length() == 0) {
        refreshEsp32CamIP();
      }

      if (esp32CamIP.length() > 0) {
        Serial.print("PHOTO_URL http://");
        Serial.print(esp32CamIP);
        Serial.println("/capture");
      } else {
        Serial.println("PHOTO_ERR ESP32-CAM IP unknown - wait for ESP32 boot or check Serial2 wiring on Mega pins 16/17");
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

// ── Setup & loop ─────────────────────────────────────────────────────────────
void setup() {
  pinMode(ENABLE_PIN, OUTPUT);
  //digitalWrite(ENABLE_PIN, LOW);

  Serial.begin(9600);
  Serial2.begin(9600);
  arm.begin();

  if (loadCalFromEEPROM()) {
    Serial.println("Board calibration loaded from EEPROM.");
  } else {
    Serial.println("No saved board calibration. Run `cal` to set corners.");
  }

  Serial.println("f/b = single step X | w/s = single step Y | u/d = single step Z");
  Serial.println("home | moveXY x y | moveZ z | moveXYZ x y z | pos");
  Serial.println("OG/CG = open/close gripper | v/c = open/close gripper | GS = gripper status");
  Serial.println("cm = controller mode (w/a/s/d=XY, u/j=Z, c/v=gripper, q=exit)");
  Serial.println("cal = board calibration wizard | calClear = wipe EEPROM cal");
  Serial.println("calTrash = calibrate only trash XY (keeps H1/A1/H8)");
  Serial.println("setH1 / setA1 / setH8 / setTrash = capture corners/trash | goto <sq|trash> | boardInfo");
  Serial.println("pick <piece> <sq> | put <piece> <sq|trash>  (pieces: pawn knight bishop rook queen king)");
}

void loop() {
  updateDrivers();

  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;

    // In cm / cal mode, action keys dispatch immediately (no Enter needed) so
    // that holding the key auto-repeats into continuous motion. Multi-char
    // commands still work because their letters aren't action keys.
    if (controllerMode && isCmKey(c)) {
      handleCommand(String(c));
      continue;
    }
    if (calibrationMode && isCalKey(c)) {
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

  while (Serial2.available()) {
    char c = (char)Serial2.read();
    if (c == '\r') continue;
    if (c == '\n') {
      serial1Buf.trim();
      updateEsp32CamIPFromLine(serial1Buf);
      serial1Buf = "";
    } else {
      serial1Buf += c;
    }
  }
}
