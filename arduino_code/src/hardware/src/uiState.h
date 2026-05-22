#ifndef UI_STATE_H
#define UI_STATE_H

#include <Arduino.h>

// Enums for UI states
enum UIMode {
    BOOT,
    MENU,
    DIFFICULTY,
    MANUAL_CONTROL,
    MANUAL_ACTIVE,
    CALIBRATION,
    GAME,
    ERROR,
    COLOR_SELECT,  // 8 — added at end so ERROR stays 7
    GAME_OVER,     // 9
    PROMOTION      // 10
};

enum PromotionPiece {
    PROMO_QUEEN,
    PROMO_ROOK,
    PROMO_BISHOP,
    PROMO_KNIGHT
};

enum GameOverReason {
    GAME_OVER_WHITE_WIN,
    GAME_OVER_BLACK_WIN,
    GAME_OVER_STALEMATE,
    GAME_OVER_DRAW
};

enum MenuItem {
    START_GAME,
    CALIBRATION_ITEM,
    MANUAL_CONTROL_ITEM
};


enum ControlTarget {
    JOINT1,
    JOINT2,
    LEADSCREW,
    GRIPPER,
    BACK_TO_MENU
};

enum GripperAction {
    GRIPPER_OPEN,
    GRIPPER_CLOSE
};

enum PlayerTurn {
    WHITE,
    BLACK
};

enum GameStatus {
    WAITING_PLAYER,
    THINKING,
    MOVING,
};


class UIState {
public:
    UIState();
    
    // Mode methods
    void setMode(UIMode mode);
    UIMode getMode() const;
    void back();
    
    // Menu navigation
    void menuNext();
    void menuPrev();
    void selectCurrentMenuItem();
    MenuItem getSelectedMenuItem() const;

    // Difficulty navigation and setting (numeric 1–20)
    void difficultyNext();
    void difficultyPrev();
    int getDifficulty() const;

    // temporary Difficulty
    void enterDifficulty();
    void commitDifficulty();
    void cancelDifficulty();
    int getTempDifficulty() const;

    // ControlTarget navigation and setting
    void controlNext();
    void controlPrev();
    void setControlTarget(ControlTarget target);
    ControlTarget getSelectedControlTarget() const;
    void enterSelectedControlTarget();

    // Gripper action in MANUAL_ACTIVE
    void gripperNext();
    void gripperPrev();
    GripperAction getGripperAction() const;
  
    void setTurn(PlayerTurn turn);
    PlayerTurn getTurn() const;

    void setGameStatus(GameStatus status);
    GameStatus getGameStatus() const;
    void setBotMove(const String& moveStr);
    void setBotPromoting(char piece);  // piece: 'Q','R','B','N'
    void setInCheck();

    // Color selection (COLOR_SELECT mode)
    void colorToggle();
    PlayerTurn getSelectedColor() const;

    void setErrorMessage(const String& msg);
    void clearError();
    bool tickScroll();
    UIMode getModeBeforeError() const;

    void setGameOver(GameOverReason reason);
    GameOverReason getGameOverReason() const;

    // Promotion selection (PROMOTION mode)
    void promotionNext();
    void promotionPrev();
    PromotionPiece getSelectedPromotion() const;
    char getPromotionLetter() const;

    // Display methods
    String getLine1() const;
    String getLine2() const;

private:
    UIMode currentMode;
    MenuItem selectedMenuItem;
    int currentDifficulty;
    int tempDifficulty;
    ControlTarget selectedControlTarget;
    GripperAction gripperAction;
    PlayerTurn currentTurn;
    GameStatus gameStatus;
    UIMode modeBeforeError;
    PlayerTurn selectedColor;
    GameOverReason gameOverReason;
    String errorMessage;
    int scrollOffset;
    unsigned long lastScrollMs;
    String botMoveStr;
    bool isPromoting;
    char promotingPiece;
    bool inCheck;
    PromotionPiece selectedPromotion;

    static const int MENU_COUNT = 3;
    static const int DIFFICULTY_MIN = 1;
    static const int DIFFICULTY_MAX = 20;
    static const int CONTROL_COUNT = 5;
    static const int GRIPPER_CONTROL_COUNT = 2;
};

#endif