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
    COLOR_SELECT  // 8 — added at end so ERROR stays 7
};

enum MenuItem {
    START_GAME,
    DIFFICULTY_ITEM,
    CALIBRATION_ITEM,
    MANUAL_CONTROL_ITEM
};

enum Difficulty {
    EASY,
    MEDIUM,
    HARD
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

    // Difficulty navigation and setting
    void difficultyNext();
    void difficultyPrev();
    Difficulty getDifficulty() const;

     // temporary Difficulty
    void enterDifficulty();
    void commitDifficulty();
    void cancelDifficulty();
    Difficulty getTempDifficulty() const;

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

    // Color selection (COLOR_SELECT mode)
    void colorToggle();
    PlayerTurn getSelectedColor() const;

    void clearError();

    // Display methods
    String getLine1() const;
    String getLine2() const;

private:
    UIMode currentMode;
    MenuItem selectedMenuItem;
    Difficulty currentDifficulty;
    Difficulty tempDifficulty;
    ControlTarget selectedControlTarget;
    GripperAction gripperAction;
    PlayerTurn currentTurn;
    GameStatus gameStatus;
    UIMode modeBeforeError;
    PlayerTurn selectedColor;
    
    static const int MENU_COUNT = 4;
    static const int DIFFICULTY_COUNT = 3;
    static const int CONTROL_COUNT = 5;
    static const int GRIPPER_CONTROL_COUNT = 2;
};

#endif