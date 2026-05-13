#ifndef ENABLE_DRIVER_H
#define ENABLE_DRIVER_H

#include <Arduino.h>
#include "pins.h"

void enableDrivers();
void disableDrivers();
void beforeMove();
void afterMove();
void updateDrivers();

#endif