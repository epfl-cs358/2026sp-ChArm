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

    // Call frequently from loop(): periodically re-initializes the HD44780
    // interface so a noise glitch that desyncs the 4-bit nibble counter
    // self-heals instead of staying garbled until reset.
    void tick();

private:
    LiquidCrystal lcd;
    char lastLine1[17];
    char lastLine2[17];
    unsigned long lastResyncMs;

    static const unsigned long RESYNC_INTERVAL_MS = 1000;
};

#endif