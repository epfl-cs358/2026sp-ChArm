#include "uiController.h"
#include "buttonInput.h"
#include "lcdDisplay.h"
#include "scaraJoint.h"
#include "leadScrew.h"
#include "scaraArm.h"
#include "gripper.h"

//extern void calibrate();
extern ScaraJoint joint1;
extern ScaraJoint joint2;
extern LeadScrew leadScrew;
extern Gripper gripper;
extern ScaraArm arm;

static const float MANUAL_JOINT_STEP_DEG = 2.0f;
static const float MANUAL_Z_STEP_MM = 0.5f;

UIController::UIController(ButtonInput& buttonInput, UIState& uiState, LCDDisplay& lcd, Stream& serial)
    : buttonInput(buttonInput), uiState(uiState), lcd(lcd), serial(serial), rxBuffer() {
    this->waitingForBoard = false; 
    this->boardRequestTs = 0;
    this->lastMode = uiState.getMode();
}

void UIController::begin(unsigned long baud) {
    buttonInput.begin();
    lcd.begin();
    uiState.setMode(MENU);
    lcd.update(uiState.getLine1(), uiState.getLine2());
}

void UIController::loop() {

    // detect mode entry for one-shot actions (e.g., auto-start calibration)
    UIMode currentMode = uiState.getMode();
    if (currentMode != lastMode) {
        if (currentMode == CALIBRATION) {
            // auto-start calibration immediately on entering CALIBRATION
            sendMessage("CALIBRATE_START");
            //calibrate();
            sendMessage("CALIBRATE_DONE");
            uiState.setMode(MENU);
            currentMode = uiState.getMode();
        }
        lastMode = currentMode;
        pendingLcdUpdate = true;
    }

    // handle incoming serial lines
    while (serial.available()) {
        char c = (char)serial.read();
        if (c == '\n') {
            String line = rxBuffer;
            rxBuffer = "";
            line.trim();
            if (line.length()) { processLine(line); pendingLcdUpdate = true; }
        } else if (c != '\r') {
            rxBuffer += c;
            if (rxBuffer.length() > 256) rxBuffer = rxBuffer.substring(rxBuffer.length() - 256);
        }
    }

    // handle one button event per loop
    InputEvent ev = buttonInput.readEvent();
    if (ev != INPUT_NONE) {
        pendingLcdUpdate = true;
        UIMode mode = uiState.getMode();
        switch (mode) {
            case MENU:
                if (ev == INPUT_NEXT) uiState.menuNext();
                else if (ev == INPUT_PREV) uiState.menuPrev();
                else if (ev == INPUT_SELECT) {
                    if (uiState.getSelectedMenuItem() == START_GAME) {
                        uiState.setMode(COLOR_SELECT);
                    } else {
                        uiState.selectCurrentMenuItem();
                    }
                }
                break;

            case COLOR_SELECT:
                if (ev == INPUT_NEXT || ev == INPUT_PREV) uiState.colorToggle();
                else if (ev == INPUT_SELECT) {
                    sendMessage(String("SET_COLOR ") + String((int)uiState.getSelectedColor()));
                    sendMessage("CHECK_BOARD");
                    waitingForBoard = true;
                    boardRequestTs = millis();
                }
                break;

            case DIFFICULTY:
                if (ev == INPUT_NEXT) uiState.difficultyNext();
                else if (ev == INPUT_PREV) uiState.difficultyPrev();
                else if (ev == INPUT_SELECT) {
                    uiState.commitDifficulty();
                    sendMessage(String("SET_DIFFICULTY ") + String((int)uiState.getDifficulty()));
                }
                break;

            case CALIBRATION:
                // Calibration is started automatically on mode entry
                break;

            case MANUAL_CONTROL:
                if (ev == INPUT_NEXT) uiState.controlNext();
                else if (ev == INPUT_PREV) uiState.controlPrev();
                else if (ev == INPUT_SELECT) uiState.enterSelectedControlTarget();
                break;

            case MANUAL_ACTIVE:
                if (uiState.getSelectedControlTarget() == JOINT1) {
                    if (ev == INPUT_NEXT); //joint1.moveBy(MANUAL_JOINT_STEP_DEG);
                    else if (ev == INPUT_PREV); //joint1.moveBy(-MANUAL_JOINT_STEP_DEG);
                    else if (ev == INPUT_SELECT) {
                        //arm.sync();
                        uiState.setMode(MANUAL_CONTROL);
                    }
                } else if (uiState.getSelectedControlTarget() == JOINT2) {
                    if (ev == INPUT_NEXT); //joint2.moveBy(MANUAL_JOINT_STEP_DEG);
                    else if (ev == INPUT_PREV); //joint2.moveBy(-MANUAL_JOINT_STEP_DEG);
                    else if (ev == INPUT_SELECT) {
                        //arm.sync();
                        uiState.setMode(MANUAL_CONTROL);
                    }
                } else if (uiState.getSelectedControlTarget() == LEADSCREW) {
                    if (ev == INPUT_NEXT); //leadScrew.moveBy_mm(MANUAL_Z_STEP_MM);
                    else if (ev == INPUT_PREV); //leadScrew.moveBy_mm(-MANUAL_Z_STEP_MM);
                    else if (ev == INPUT_SELECT) {
                        //arm.sync();
                        uiState.setMode(MANUAL_CONTROL);
                    }
                } else if (uiState.getSelectedControlTarget() == GRIPPER) {
                    if (ev == INPUT_NEXT) {
                        uiState.gripperNext();
                    } else if (ev == INPUT_PREV) {
                        uiState.gripperPrev();
                    } else if (ev == INPUT_SELECT) {
                        if (uiState.getGripperAction() == GRIPPER_OPEN) {
                            //gripper.open();
                        } else {
                            //gripper.close();
                        }
                        uiState.setMode(MANUAL_CONTROL);
                    }
                }
                break;

            case GAME:
                if (ev == INPUT_SELECT && uiState.getGameStatus() == WAITING_PLAYER) {
                    sendMessage("PLAYER_DONE");
                }
                break;

            case ERROR:
                if (ev == INPUT_SELECT) {
                    uiState.clearError();
                }
                break;

            default:
                break;
        }
    }

    // handle board check timeout
    if (waitingForBoard && (millis() - boardRequestTs > boardTimeoutMs)) {
        waitingForBoard = false;
        uiState.setMode(ERROR);
        sendMessage("BOARD_TIMEOUT");
        pendingLcdUpdate = true;
    }

    if (pendingLcdUpdate) {
        lcd.update(uiState.getLine1(), uiState.getLine2());
        pendingLcdUpdate = false;
    }
}

void UIController::processLine(const String& line) {
    if (line.equalsIgnoreCase("GET_STATE")) {
        sendState();
    } else if (line.startsWith("SET_MODE ")) {
        int n = line.substring(9).toInt();
        uiState.setMode((UIMode)n);
        sendMessage("OK");
    } else if (line.equalsIgnoreCase("BOARD_OK")) {
        if (waitingForBoard) {
            waitingForBoard = false;
            uiState.setMode(GAME);
            uiState.setGameStatus(WAITING_PLAYER);
            sendMessage("BOARD_OK_ACK");
        }
    } else if (line.equalsIgnoreCase("BOARD_FAIL")) {
        if (waitingForBoard) {
            waitingForBoard = false;
            uiState.setMode(ERROR);
            sendMessage("BOARD_FAIL_ACK");
        }
    } else if (line.equalsIgnoreCase("ERROR_CLEAR")) {
        uiState.clearError();
    } else if (line.equalsIgnoreCase("BOT_THINKING")) {
        uiState.setGameStatus(THINKING);
    } else if (line.equalsIgnoreCase("BOT_MOVING")) {
        uiState.setGameStatus(MOVING);
    } else if (line.equalsIgnoreCase("PLAYER_TURN_WHITE")) {
        uiState.setTurn(WHITE);
        uiState.setGameStatus(WAITING_PLAYER);
    } else if (line.equalsIgnoreCase("PLAYER_TURN_BLACK")) {
        uiState.setTurn(BLACK);
        uiState.setGameStatus(WAITING_PLAYER);
    } else {
        handleHostCommand(line);
    }
}

void UIController::handleHostCommand(const String& cmd) {
    // Unknown commands from host
    sendMessage("UNKNOWN_CMD");
}

void UIController::sendState() {
    serial.println(serializeState());
}

void UIController::sendMessage(const String& msg) {
    serial.println(msg);
}

String UIController::serializeState() const {
    String s = "STATE ";
    s += "m:" + String((int)uiState.getMode());
    s += " menu:" + String((int)uiState.getSelectedMenuItem());
    s += " diff:" + String((int)uiState.getDifficulty());
    s += " control:" + String((int)uiState.getSelectedControlTarget());
    s += " grip:" + String((int)uiState.getGripperAction());
    s += " turn:" + String((int)uiState.getTurn());
    s += " status:" + String((int)uiState.getGameStatus());
    s += " | ";
    s += uiState.getLine1();
    s += " | ";
    s += uiState.getLine2();
    return s;
}