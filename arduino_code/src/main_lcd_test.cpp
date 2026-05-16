#include <Arduino.h>
#include "hardware/src/pins.h"
#include "hardware/src/buttonInput.h"
#include "hardware/src/lcdDisplay.h"

ButtonInput buttonInput(CLK_PIN, DT_PIN, SW_PIN);
LCDDisplay lcd(RS_PIN, E_PIN, D4_PIN, D5_PIN, D6_PIN, D7_PIN);

static const char* SCREENS[][2] = {
    {"  LCD Test",       "Turn or press btn "},
    {"  Hello World!",   "  Line 2 works!   "},
    {"  NEXT ->",        "  turn right      "},
    {"  <- PREV",        "  turn left       "},
    {"  SELECT",         "  press button    "},
};
static const int NUM_SCREENS = 5;

static int currentScreen = 0;
static unsigned long eventCount = 0;

static void showScreen() {
    lcd.update(SCREENS[currentScreen][0], SCREENS[currentScreen][1]);
}

void setup() {
    Serial.begin(9600);
    buttonInput.begin();
    lcd.begin();

    showScreen();
    Serial.println("LCD + button test ready");
}

void loop() {
    InputEvent event = buttonInput.readEvent();

    if (event == INPUT_NEXT) {
        currentScreen = (currentScreen + 1) % NUM_SCREENS;
        eventCount++;
        showScreen();
        Serial.print("NEXT -> screen ");
        Serial.println(currentScreen);
    } else if (event == INPUT_PREV) {
        currentScreen = (currentScreen - 1 + NUM_SCREENS) % NUM_SCREENS;
        eventCount++;
        showScreen();
        Serial.print("PREV -> screen ");
        Serial.println(currentScreen);
    } else if (event == INPUT_SELECT) {
        eventCount++;
        lcd.update("Events: " + String(eventCount), "SELECT pressed    ");
        Serial.print("SELECT, total events: ");
        Serial.println(eventCount);
    }
}
