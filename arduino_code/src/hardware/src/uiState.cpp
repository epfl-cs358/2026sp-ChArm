#include "uiState.h"

UIState::UIState() {
    this->currentMode = BOOT;
    this->selectedMenuItem = START_GAME;
    this->currentDifficulty = MEDIUM;
    this->tempDifficulty = currentDifficulty;
    this->selectedControlTarget = JOINT1;
    this->gripperAction = GRIPPER_OPEN;
    this->currentTurn = WHITE;
    this->gameStatus = WAITING_PLAYER;
    this->modeBeforeError = MENU;
}

void UIState::setMode(UIMode mode) {
    if (mode == ERROR && currentMode != ERROR) {
        modeBeforeError = currentMode;
    }
    currentMode = mode;
}

UIMode UIState::getMode() const {
    return currentMode;
}

void UIState::back() {
    switch (currentMode) {
        case DIFFICULTY:
            cancelDifficulty();
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
            clearError();
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
            enterDifficulty();
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
    tempDifficulty = (Difficulty)((tempDifficulty + 1) % DIFFICULTY_COUNT);
}

void UIState::difficultyPrev() {
    tempDifficulty = (Difficulty)((tempDifficulty + DIFFICULTY_COUNT - 1) % DIFFICULTY_COUNT);
}

Difficulty UIState::getDifficulty() const {
    return currentDifficulty;
}

void UIState::enterDifficulty() {
    tempDifficulty = currentDifficulty;
    setMode(DIFFICULTY);
}

void UIState::commitDifficulty() {
    currentDifficulty = tempDifficulty;
    setMode(MENU);
}

void UIState::cancelDifficulty() {
    // discard temp and return to menu
    tempDifficulty = currentDifficulty;
    setMode(MENU);
}

Difficulty UIState::getTempDifficulty() const {
    return tempDifficulty;
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
    if (selectedControlTarget == BACK_TO_MENU) {
        setMode(MENU);
    } else {
        setMode(MANUAL_ACTIVE);
    }
}

void UIState::gripperNext() {
    gripperAction = (GripperAction)((gripperAction + 1) % GRIPPER_CONTROL_COUNT);
}

void UIState::gripperPrev() {
    gripperAction = (GripperAction)((gripperAction + GRIPPER_CONTROL_COUNT - 1) % GRIPPER_CONTROL_COUNT);
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

void UIState::clearError() {
    if (currentMode == ERROR) {
        currentMode = modeBeforeError;
    }
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
                case BACK_TO_MENU:
                    return "Return to Menu";
            }
            return "?";

        case CALIBRATION:
            return "Calibration";

        case GAME:
            return currentTurn == WHITE ? "White Turn" : "Black Turn";

        case ERROR:
            return "ERR: check board";

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
            switch (tempDifficulty) {
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
                case BACK_TO_MENU: return "> Back";
            }
            return "?";

        case MANUAL_ACTIVE:
            if (selectedControlTarget == GRIPPER) {
                return gripperAction == GRIPPER_OPEN ? "> Open" : "> Close";
            }
            return "Press to go Back";

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