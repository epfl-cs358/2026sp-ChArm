#include "uiController_esp32.h"

UIControllerESP32::UIControllerESP32(ButtonInput& buttonInput, UIState& uiState, LCDDisplay& lcd)
    : buttonInput(buttonInput), uiState(uiState), lcd(lcd),
      rxBuffer(""), waitingForBoard(false), pendingLcdUpdate(false),
      lastMode(BOOT), boardRequestTs(0) {}

void UIControllerESP32::begin() {
    buttonInput.begin();
    lcd.begin();
    uiState.setMode(MENU);
    lcd.update(uiState.getLine1(), uiState.getLine2());
}

void UIControllerESP32::loop(WiFiClient& client) {
    // One-shot actions on mode entry
    UIMode currentMode = uiState.getMode();
    if (currentMode != lastMode) {
        if (currentMode == CALIBRATION) {
            sendMessage(client, "CALIBRATION");
        }
        lastMode = currentMode;
        pendingLcdUpdate = true;
    }

    // Read lines from Python
    while (client.available()) {
        char c = (char)client.read();
        if (c == '\r') continue;
        if (c == '\n') {
            String line = rxBuffer;
            rxBuffer = "";
            line.trim();
            if (line.length()) { processLine(client, line); pendingLcdUpdate = true; }
        } else {
            rxBuffer += c;
            if (rxBuffer.length() > 256)
                rxBuffer = rxBuffer.substring(rxBuffer.length() - 256);
        }
    }

    // Handle one button event
    handleButtons(client);

    // Board-check timeout
    if (waitingForBoard && (millis() - boardRequestTs > BOARD_TIMEOUT_MS)) {
        waitingForBoard = false;
        uiState.setMode(ERROR);
        sendMessage(client, "BOARD_TIMEOUT");
        pendingLcdUpdate = true;
    }

    if (uiState.tickScroll()) pendingLcdUpdate = true;

    if (pendingLcdUpdate) {
        lcd.update(uiState.getLine1(), uiState.getLine2());
        pendingLcdUpdate = false;
    }
}

void UIControllerESP32::sendMessage(WiFiClient& client, const String& msg) {
    if (client && client.connected()) {
        client.println(msg);
        Serial.print("[ESP32->PY] "); Serial.println(msg);
    }
}

// Process one line received from Python
void UIControllerESP32::processLine(WiFiClient& client, const String& line) {
    Serial.print("[PY->ESP32] "); Serial.println(line);

    if (line.equalsIgnoreCase("OK")) {
        return;

    } else if (line.equalsIgnoreCase("BOARD_OK")) {
        if (waitingForBoard) {
            waitingForBoard = false;
            uiState.setMode(GAME);
            uiState.setGameStatus(WAITING_PLAYER);
            sendMessage(client, "BOARD_OK_ACK");
        }

    } else if (line.equalsIgnoreCase("BOARD_FAIL")) {
        if (waitingForBoard) {
            waitingForBoard = false;
            uiState.setMode(ERROR);
            sendMessage(client, "BOARD_FAIL_ACK");
        }

    } else if (line.equalsIgnoreCase("BOT_THINKING")) {
        uiState.setGameStatus(THINKING);
        pendingLcdUpdate = true;

    } else if (line.startsWith("BOT_MOVE ")) {
        String label = line.substring(9);
        label.trim();
        uiState.setBotMove(label);
        pendingLcdUpdate = true;

    } else if (line.equalsIgnoreCase("BOT_MOVING")) {
        uiState.setGameStatus(MOVING);
        pendingLcdUpdate = true;

    } else if (line.startsWith("BOT_PROMOTING ")) {
        char piece = line.charAt(14);
        uiState.setBotPromoting(piece);
        pendingLcdUpdate = true;

    } else if (line.equalsIgnoreCase("PLAYER_TURN_WHITE")) {
        uiState.setTurn(WHITE);
        uiState.setGameStatus(WAITING_PLAYER);
        pendingLcdUpdate = true;

    } else if (line.equalsIgnoreCase("PLAYER_TURN_BLACK")) {
        uiState.setTurn(BLACK);
        uiState.setGameStatus(WAITING_PLAYER);
        pendingLcdUpdate = true;

    } else if (line.equalsIgnoreCase("MOVE_DONE")) {
        uiState.setGameStatus(WAITING_PLAYER);
        pendingLcdUpdate = true;

    } else if (line.equalsIgnoreCase("CHECK")) {
        uiState.setInCheck();
        pendingLcdUpdate = true;

    } else if (line.startsWith("GAME_OVER ")) {
        String reason = line.substring(10);
        reason.trim();
        if (reason.equalsIgnoreCase("WHITE_WIN")) {
            uiState.setGameOver(GAME_OVER_WHITE_WIN);
        } else if (reason.equalsIgnoreCase("BLACK_WIN")) {
            uiState.setGameOver(GAME_OVER_BLACK_WIN);
        } else if (reason.equalsIgnoreCase("STALEMATE")) {
            uiState.setGameOver(GAME_OVER_STALEMATE);
        } else {
            uiState.setGameOver(GAME_OVER_DRAW);
        }
        pendingLcdUpdate = true;
        sendMessage(client, "OK");

    } else if (line.startsWith("ERROR_MSG ")) {
        String msg = line.substring(10);
        msg.trim();
        uiState.setErrorMessage(msg);
        pendingLcdUpdate = true;

    } else if (line.equalsIgnoreCase("PROMOTION_NEEDED")) {
        uiState.setMode(PROMOTION);
        pendingLcdUpdate = true;

    } else if (line.startsWith("SET_MODE ")) {
        int n = line.substring(9).toInt();
        uiState.setMode((UIMode)n);
        sendMessage(client, "OK");

    } else {
        Serial.print("[ESP32] Unknown line ignored: "); Serial.println(line);
    }
}

// Handle one button event, mirroring uiController.cpp where useful.
void UIControllerESP32::handleButtons(WiFiClient& client) {
    InputEvent ev = buttonInput.readEvent();
    if (ev == INPUT_NONE) return;

    pendingLcdUpdate = true;
    UIMode mode = uiState.getMode();

    switch (mode) {
        case MENU:
            if      (ev == INPUT_NEXT)   uiState.menuNext();
            else if (ev == INPUT_PREV)   uiState.menuPrev();
            else if (ev == INPUT_SELECT) uiState.selectCurrentMenuItem();
            break;

        case COLOR_SELECT:
            if (ev == INPUT_NEXT || ev == INPUT_PREV)
                uiState.colorToggle();
            else if (ev == INPUT_SELECT) {
                waitingForBoard  = true;
                boardRequestTs   = millis();
                sendMessage(client, String("SET_COLOR ") + String((int)uiState.getSelectedColor()));
                sendMessage(client, "CHECK_BOARD");
            }
            break;

        case DIFFICULTY:
            if      (ev == INPUT_NEXT)   uiState.difficultyNext();
            else if (ev == INPUT_PREV)   uiState.difficultyPrev();
            else if (ev == INPUT_SELECT) {
                uiState.commitDifficulty();
                sendMessage(client, String("SET_DIFFICULTY ") + String((int)uiState.getDifficulty()));
            }
            break;

        case CALIBRATION:
            // CALIBRATION is sent to Python on mode entry; nothing more on button press.
            break;

        case MANUAL_CONTROL:
            if      (ev == INPUT_NEXT)   uiState.controlNext();
            else if (ev == INPUT_PREV)   uiState.controlPrev();
            else if (ev == INPUT_SELECT) uiState.enterSelectedControlTarget();
            break;

        case MANUAL_ACTIVE: {
            ControlTarget target = uiState.getSelectedControlTarget();
            if (target == GRIPPER) {
                if      (ev == INPUT_NEXT)   uiState.gripperNext();
                else if (ev == INPUT_PREV)   uiState.gripperPrev();
                else if (ev == INPUT_SELECT) {
                    sendMessage(client,
                        uiState.getGripperAction() == GRIPPER_OPEN
                            ? "MANUAL_GRIPPER_OPEN"
                            : "MANUAL_GRIPPER_CLOSE");
                    uiState.setMode(MANUAL_CONTROL);
                }
            } else {
                // Joint / Z jog: send command to Python, which relays to the Mega.
                if (ev == INPUT_NEXT || ev == INPUT_PREV) {
                    const char* dir = (ev == INPUT_NEXT) ? "FWD" : "BWD";
                    String cmd;
                    if      (target == JOINT1)    cmd = String("MANUAL_JOINT1_") + dir;
                    else if (target == JOINT2)    cmd = String("MANUAL_JOINT2_") + dir;
                    else if (target == LEADSCREW) cmd = String("MANUAL_Z_") + dir;
                    sendMessage(client, cmd);
                } else if (ev == INPUT_SELECT) {
                    uiState.setMode(MANUAL_CONTROL);
                }
            }
            break;
        }

        case PROMOTION:
            if      (ev == INPUT_NEXT)   uiState.promotionNext();
            else if (ev == INPUT_PREV)   uiState.promotionPrev();
            else if (ev == INPUT_SELECT) {
                String msg = String("PROMOTION_CHOICE ") + String(uiState.getPromotionLetter());
                sendMessage(client, msg);
                uiState.setMode(GAME);
            }
            break;

        case GAME:
            if (ev == INPUT_SELECT && uiState.getGameStatus() == WAITING_PLAYER)
                sendMessage(client, "PLAYER_DONE");
            break;

        case ERROR:
            if (ev == INPUT_SELECT) {
                if (uiState.getModeBeforeError() == COLOR_SELECT) {
                    // Board setup failed — retry the check without asking for color again.
                    uiState.clearError();
                    waitingForBoard = true;
                    boardRequestTs = millis();
                    sendMessage(client, "CHECK_BOARD");
                } else {
                    uiState.clearError();
                }
            }
            break;

        default:
            break;
    }
}
