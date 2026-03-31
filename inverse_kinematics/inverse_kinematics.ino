#include <AccelStepper.h>
#include <Servo.h>

// Steps per revolution for NEMA 17 (200 steps * microstepping)
// Adjust MICROSTEP to match the driver (pins)
#define MICROSTEP TODO
#define STEPS_PER_REV (200 * MICROSTEP)

// Degrees per step
#define DEG_PER_STEP (360.0 / STEPS_PER_REV)

// Z-axis: steps per mm (depends on the lead screw pitch)
#define Z_STEPS_PER_MM TODO

#define j1 287.5
#define j2 250.0
#define j3 290.0

#define GRIPPER_LENGTH 100.0

AccelStepper stepperZ (TODO);
AccelStepper stepperJ1(TODO);
AccelStepper stepperJ2(TODO);

Servo gripper;

//State
long currentX = 0;
long currentY = 0;
long currentZ = 0;
float currentTheta1 = 0.0;
float currentTheta2 = 0.0;
int gripperPos = 90;

void inverseKinematics(float x, float y) {
  float d = (x * x + y * y - j1 * j1 - j2 * j2) / (2.0 * j1 * j2);

  // Check reachability
  if (d < -1.0 || d > 1.0) {
      Serial.println("ERROR: Target out of reach!");
      return;
  }

  currentX = x;
  currentY = y;

  float theta2 = -acos((pow(j1, 2) + pow(j2, 2) - pow(x, 2) - pow(y, 2)) /  (2*j1*j2));

  float theta1 = atan2((j2 * sin(theta2)) / (j1 + j2 * cos(theta2))) + atan(y / x);

  theta2 = theta2 * 180.0 / PI;
  theta1 = theta1 * 180.0 / PI;

  // Angles adjustment depending where the final coordinate x,y is
  if (x >= 0 && y <= 0) {   // top-right
    theta1 = 90 - theta1;
  }
  if (x < 0 && y < 0) {    // top-left
    theta1 = 90 - theta1;
  }
  if (x < 0 && y > 0) {    // bottom-left
    theta1 = 270 - theta1;
  }
  if (x > 0 && y > 0) {    // bottom-right
    theta1 = -90 - theta1;
  }
  if (x < 0 && y == 0) {   // directly left
    theta1 = 270 + theta1;
  }

  currentTheta1 = theta1
  currentTheta2 = theta2
}

long degreesToSteps(float deg) {
    return (long)(deg / DEG_PER_STEP);
}

long mmToSteps(float mm) {
    return (long)(mm * Z_STEPS_PER_MM);
}

void moveZ(float z_mm) {
    // The carriage must sit HIGHER than the target by the gripper length
    // so the tip ends up exactly at z_mm
    float carriageZ = z_mm + GRIPPER_LENGTH;

    stepperZ.moveTo(mmToSteps(carriageZ));
    currentZ = z_mm;
}

// Move to XY position using inverse kinematics
void moveXY(float x, float y) {
    stepperJ1.moveTo(degreesToSteps(currentTheta1));
    stepperJ2.moveTo(degreesToSteps(currentTheta2));
}

void moveTo(float x, float y, float z_mm) {
    moveZ(z_mm);
    moveXY(x, y);
}

// Block until all motors reach their targets
void waitForMotors() {
    while (stepperZ.distanceToGo()  != 0 ||
           stepperJ1.distanceToGo() != 0 ||
           stepperJ2.distanceToGo() != 0) {
        stepperZ.run();
        stepperJ1.run();
        stepperJ2.run();
    }
}

void openGripper() {
    gripper.write(0);    // Adjust angle for the servo/gripper
    gripperPos = 0;
    delay(500);
}

void closeGripper() {
    gripper.write(90);   // Adjust angle for the servo/gripper
    gripperPos = 90;
    delay(500);
}

void parseSerial() {
    if (!Serial.available()) return;

    String cmd = Serial.readStringUntil('\n');
    cmd.trim();

    if (cmd.startsWith("G")) {
        float x = currentX, y = currentY, z = currentZ;
        int xi = cmd.indexOf('X');
        int yi = cmd.indexOf('Y');
        int zi = cmd.indexOf('Z');
        if (xi >= 0) x = cmd.substring(xi + 1).toFloat();
        if (yi >= 0) y = cmd.substring(yi + 1).toFloat();
        if (zi >= 0) z = cmd.substring(zi + 1).toFloat();
        moveTo(x, y, z);
        waitForMotors();

    } else if (cmd == "OG") {
        openGripper();

    } else if (cmd == "CG") {
        closeGripper();

    } else {
        Serial.println("Unknown command.");
    }
}

