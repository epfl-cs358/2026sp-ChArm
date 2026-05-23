#include "uiState.h"

UIState::UIState() {
    this->currentMode = BOOT;
    this->selectedMenuItem = START_GAME;
    this->currentDifficulty = 10;
    this->tempDifficulty = 10;
    this->selectedControlTarget = JOINT1;
    this->gripperAction = GRIPPER_OPEN;
    this->currentTurn = WHITE;
    this->gameStatus = WAITING_PLAYER;
    this->modeBeforeError = MENU;
    this->selectedColor = WHITE;
    this->gameOverReason = GAME_OVER_DRAW;
    this->errorMessage = "";
    this->scrollOffset = 0;
    this->lastScrollMs = 0;
    this->botMoveStr = "";
    this->isPromoting = false;
    this->promotingPiece = 'Q';
    this->inCheck = false;
    this->selectedPromotion = PROMO_QUEEN;
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
        case COLOR_SELECT:
            setMode(MENU);
            break;
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
    tempDifficulty = (tempDifficulty >= DIFFICULTY_MAX) ? DIFFICULTY_MIN : tempDifficulty + 1;
}

void UIState::difficultyPrev() {
    tempDifficulty = (tempDifficulty <= DIFFICULTY_MIN) ? DIFFICULTY_MAX : tempDifficulty - 1;
}

int UIState::getDifficulty() const {
    return currentDifficulty;
}

void UIState::enterDifficulty() {
    tempDifficulty = currentDifficulty;
    setMode(DIFFICULTY);
}

void UIState::commitDifficulty() {
    currentDifficulty = tempDifficulty;
    setMode(COLOR_SELECT);
}

void UIState::cancelDifficulty() {
    // discard temp and return to menu
    tempDifficulty = currentDifficulty;
    setMode(MENU);
}

int UIState::getTempDifficulty() const {
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

void UIState::colorToggle() {
    selectedColor = (selectedColor == WHITE) ? BLACK : WHITE;
}

PlayerTurn UIState::getSelectedColor() const {
    return selectedColor;
}

void UIState::setGameStatus(GameStatus status) {
    if (status == WAITING_PLAYER) isPromoting = false;
    if (status == THINKING) inCheck = false;
    gameStatus = status;
}

void UIState::setInCheck() {
    inCheck = true;
}

void UIState::setBotPromoting(char piece) {
    isPromoting = true;
    promotingPiece = piece;
}

GameStatus UIState::getGameStatus() const {
    return gameStatus;
}

void UIState::setBotMove(const String& moveStr) {
    botMoveStr = moveStr;
}

void UIState::setErrorMessage(const String& msg) {
    errorMessage = msg;
    scrollOffset = 0;
    lastScrollMs = millis();
    setMode(ERROR);
}

bool UIState::tickScroll() {
    if (currentMode != ERROR || errorMessage.length() <= 16) return false;
    if (millis() - lastScrollMs >= 400) {
        lastScrollMs = millis();
        scrollOffset++;
        if (scrollOffset > (int)errorMessage.length() - 16) scrollOffset = 0;
        return true;
    }
    return false;
}

void UIState::clearError() {
    if (currentMode == ERROR) {
        currentMode = modeBeforeError;
        errorMessage = "";
        scrollOffset = 0;
    }
}

UIMode UIState::getModeBeforeError() const {
    return modeBeforeError;
}

void UIState::promotionNext() {
    selectedPromotion = (PromotionPiece)((selectedPromotion + 1) % 4);
}

void UIState::promotionPrev() {
    selectedPromotion = (PromotionPiece)((selectedPromotion + 3) % 4);
}

PromotionPiece UIState::getSelectedPromotion() const {
    return selectedPromotion;
}

char UIState::getPromotionLetter() const {
    switch (selectedPromotion) {
        case PROMO_QUEEN:  return 'Q';
        case PROMO_ROOK:   return 'R';
        case PROMO_BISHOP: return 'B';
        case PROMO_KNIGHT: return 'N';
        default:           return 'Q';
    }
}

void UIState::setGameOver(GameOverReason reason) {
    gameOverReason = reason;
    setMode(GAME_OVER);
}

GameOverReason UIState::getGameOverReason() const {
    return gameOverReason;
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

        case COLOR_SELECT:
            return "Play as...";

        case CALIBRATION:
            return "Calibration";

        case GAME:
            if (gameStatus == MOVING) return "Bot moving";
            if (inCheck)
                return currentTurn == WHITE ? "CHECK White Turn" : "CHECK Black Turn";
            return currentTurn == WHITE ? "White Turn" : "Black Turn";

        case ERROR:
            // Move-rating flashes reuse ERROR mode to show the evaluation term
            // on line 2. Relabel line 1 so a legal, evaluated move doesn't read
            // as "Illegal move !".
            if (errorMessage == "EXCELLENT!" || errorMessage == "GOOD" ||
                errorMessage == "INACCURACY" || errorMessage == "MISTAKE!" ||
                errorMessage == "BLUNDER!") {
                return "Stockfish Eval:";
            }
            return errorMessage.length() > 0 ? "Illegal move !" : "Set up ERROR";

        case GAME_OVER:
            switch (gameOverReason) {
                case GAME_OVER_WHITE_WIN: return "White Wins!";
                case GAME_OVER_BLACK_WIN: return "Black Wins!";
                case GAME_OVER_STALEMATE: return "Draw";
                case GAME_OVER_DRAW:      return "Draw";
            }
            return "Game Over";

        case PROMOTION:
            return "Promote pawn";

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
                case CALIBRATION_ITEM: return "> Calibration";
                case MANUAL_CONTROL_ITEM: return "> Manual Control";
            }
            return "?";

        case DIFFICULTY:
            return "> " + String(tempDifficulty);

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

        case COLOR_SELECT:
            return selectedColor == WHITE ? "> White" : "> Black";

        case CALIBRATION:
            return "Running...";

        case GAME:
            switch(gameStatus) {
                case WAITING_PLAYER: 
                    return "If done press OK";
                case THINKING:
                    return "BOT thinking...";
                case MOVING:
                    if (isPromoting) {
                        switch (promotingPiece) {
                            case 'Q': return "Promotes Queen";
                            case 'R': return "Promotes Rook";
                            case 'B': return "Promotes Bishop";
                            case 'N': return "Promotes Knight";
                        }
                    }
                    return botMoveStr.length() > 0 ? botMoveStr : "BOT moving...";
            }
            return "?";

        case ERROR:
            if (errorMessage.length() == 0) return "Check board";
            if (errorMessage.length() <= 16) return errorMessage;
            return errorMessage.substring(scrollOffset, scrollOffset + 16);

        case GAME_OVER:
            switch (gameOverReason) {
                case GAME_OVER_WHITE_WIN: return "Checkmate!";
                case GAME_OVER_BLACK_WIN: return "Checkmate!";
                case GAME_OVER_STALEMATE: return "Stalemate";
                case GAME_OVER_DRAW:      return "Game Over";
            }
            return "Game Over";

        case PROMOTION:
            switch (selectedPromotion) {
                case PROMO_QUEEN:  return "> Queen";
                case PROMO_ROOK:   return "> Rook";
                case PROMO_BISHOP: return "> Bishop";
                case PROMO_KNIGHT: return "> Knight";
            }
            return "> Queen";

        default:
            return "?";
  }
}