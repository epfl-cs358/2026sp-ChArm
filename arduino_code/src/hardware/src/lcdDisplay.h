#ifndef LCD_DISPLAY_H
#define LCD_DISPLAY_H

#include <Arduino.h>
#include <LiquidCrystal.h>

class LCDDisplay {
public:
    // Constructor takes the LCD pin configuration
    LCDDisplay(int rsPin, int ePin, int d4Pin, int d5Pin, int d6Pin, int d7Pin);

    void begin();

    // Update both lines; only refreshes if content changed
    void update(const String& line1, const String& line2);

    // Clear the display
    void clear();

private:
    LiquidCrystal lcd;
    char lastLine1[17];
    char lastLine2[17];
};

#endif