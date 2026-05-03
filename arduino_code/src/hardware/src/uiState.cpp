#include "uiState.h"

UIState::UIState() {
    currentMode = BOOT;
    selectedMenuItem = START_GAME;
    currentDifficulty = MEDIUM;
    selectedControlTarget = JOINT1;
    gripperAction = GRIPPER_OPEN;
    currentTurn = WHITE;
    gameStatus = WAITING_PLAYER;
}

void UIState::setMode(UIMode mode) {
    currentMode = mode;
}

UIMode UIState::getMode() const {
    return currentMode;
}

void UIState::back() {
    switch (currentMode) {
        case DIFFICULTY:
            setMode(MENU);
            break;
        case CALIBRATION:
            setMode(MENU);
            break;
        case MANUAL_CONTROL:
            setMode(MENU);
            break;
        case GAME:
            setMode(MENU);
            break;
        case ERROR:
            setMode(MENU);
            break;
        case MANUAL_ACTIVE:
            setMode(MANUAL_CONTROL);
            break;
        default:
            break;
    }
}

void UIState::menuNext() {
    selectedMenuItem = (MenuItem)((selectedMenuItem + 1) % MENU_COUNT);
}

void UIState::menuPrev() {
    selectedMenuItem = (MenuItem)((selectedMenuItem + MENU_COUNT - 1) % MENU_COUNT);
}

void UIState::selectCurrentMenuItem() {
    switch (selectedMenuItem) {
        case START_GAME:
            setMode(GAME);
            break;
        case DIFFICULTY_ITEM:
            setMode(DIFFICULTY);
            break;
        case CALIBRATION_ITEM:
            setMode(CALIBRATION);
            break;
        case MANUAL_CONTROL_ITEM:
            setMode(MANUAL_CONTROL);
            break;
    }
}

MenuItem UIState::getSelectedMenuItem() const {
    return selectedMenuItem;
}

void UIState::difficultyNext() {
    currentDifficulty = (Difficulty)((currentDifficulty + 1) % DIFFICULTY_COUNT);
}

void UIState::difficultyPrev() {
    currentDifficulty = (Difficulty)((currentDifficulty + DIFFICULTY_COUNT - 1) % DIFFICULTY_COUNT);
}

void UIState::setDifficulty(Difficulty diff) {
    currentDifficulty = diff;
}

Difficulty UIState::getDifficulty() const {
    return currentDifficulty;
}

void UIState::controlNext() {
    selectedControlTarget = (ControlTarget)((selectedControlTarget + 1) % CONTROL_COUNT);
}

void UIState::controlPrev() {
    selectedControlTarget = (ControlTarget)((selectedControlTarget + CONTROL_COUNT - 1) % CONTROL_COUNT);
}

void UIState::setControlTarget(ControlTarget target) {
    selectedControlTarget = target;
}

ControlTarget UIState::getSelectedControlTarget() const {
    return selectedControlTarget;
}

void UIState::enterSelectedControlTarget() {
    setMode(MANUAL_ACTIVE);
}

void UIState::gripperNext() {
    gripperAction = (GripperAction)((gripperAction + 1) % GRIPPER_CONTROL_COUNT);
}

void UIState::gripperPrev() {
    gripperAction = (GripperAction)((gripperAction + GRIPPER_CONTROL_COUNT - 1) % GRIPPER_CONTROL_COUNT);
}

void UIState::setGripperAction(GripperAction action) {
    gripperAction = action;
}

GripperAction UIState::getGripperAction() const {
    return gripperAction;
}


void UIState::setTurn(PlayerTurn turn) {
    currentTurn = turn;
}

PlayerTurn UIState::getTurn() const {
    return currentTurn;
}

void UIState::setGameStatus(GameStatus status) {
    gameStatus = status;
}

GameStatus UIState::getGameStatus() const {
    return gameStatus;
}

String UIState::getLine1() const {
    switch (currentMode) {
        case BOOT:
            return "ChArm";

        case MENU:
            return "Main Menu";

        case DIFFICULTY:
            return "Difficulty";

        case MANUAL_CONTROL:
            return "Manual Control";

        case MANUAL_ACTIVE:
            switch (selectedControlTarget) {
                case JOINT1: 
                    return "Control Joint1";
                case JOINT2: 
                    return "Control Joint2";
                case LEADSCREW: 
                    return "Control Z";
                case GRIPPER:   
                    return "Control Gripper";
            }
            return "?";

        case CALIBRATION:
            return "Calibration";

        case GAME:
            return currentTurn == WHITE ? "White Turn" : "Black Turn";

        case ERROR:
            return "ERROR";

        default:
            return "?";
    }
}

String UIState::getLine2() const {
    switch (currentMode) {
        case BOOT:
            return "Starting...";

        case MENU:
            switch (selectedMenuItem) {
                case START_GAME: return "> Start Game";
                case DIFFICULTY_ITEM: return "> Difficulty";
                case CALIBRATION_ITEM: return "> Calibration";
                case MANUAL_CONTROL_ITEM: return "> Manual Cotrol";
            }
            return "?";

        case DIFFICULTY:
            switch (currentDifficulty) {
                case EASY: return "> Easy";
                case MEDIUM: return "> Medium";
                case HARD: return "> Hard";
            }
            return "?";

        case MANUAL_CONTROL:
            switch (selectedControlTarget) {
                case JOINT1: return "> Joint1";
                case JOINT2: return "> Joint2";
                case LEADSCREW: return "> LeadScrew";
                case GRIPPER: return "> Gripper";
            }
            return "?";

        case MANUAL_ACTIVE:
            if (selectedControlTarget == GRIPPER) {
                return gripperAction == GRIPPER_OPEN ? "> Open" : "> Close";
            }
            return "Rotate to move";

        case CALIBRATION:
            return "Running...";

        case GAME:
            switch(gameStatus) {
                case WAITING_PLAYER: 
                    return "If done press OK";
                case THINKING:
                    return "BOT thinking...";
                case MOVING:
                    return "BOT moving...";
            }
            return "?";

        case ERROR:
            return "Check board";

        default:
            return "?";
  }
}