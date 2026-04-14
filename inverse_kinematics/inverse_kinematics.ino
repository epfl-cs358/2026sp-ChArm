#include <AccelStepper.h>
#include <Servo.h>

#define MICROSTEP 16
#define STEPS_PER_REV (200 * MICROSTEP)
#define DEG_PER_STEP (360.0 / STEPS_PER_REV)
#define Z_STEPS_PER_MM 8

// Gear ratios
#define DRIVING_TEETH  100    // TODO: recheck this value
#define JOINT_TEETH    105
#define BASE_TEETH     160

#define GEAR_RATIO_J1  ((float)DRIVING_TEETH / JOINT_TEETH)
#define GEAR_RATIO_J2  ((float)DRIVING_TEETH / JOINT_TEETH)
#define GEAR_RATIO_Z   ((float)DRIVING_TEETH / BASE_TEETH)

#define j1 250.0
#define j2 250.0
#define j3 290.0
#define GRIPPER_LENGTH 100.0

const int dirPinZ = 7;
const int dirPinY = 6;
const int dirPinX = 5;
const int stepPinZ = 4;
const int stepPinY = 3;
const int stepPinX = 2;

#define motorInterfaceType 1

AccelStepper stepperZ(motorInterfaceType, stepPinX, dirPinX);
AccelStepper stepperJ1(motorInterfaceType, stepPinY, dirPinY);
AccelStepper stepperJ2(motorInterfaceType, stepPinZ, dirPinZ);

Servo gripper;

float currentX = 0;
float currentY = 0;
float currentZ = 0;
float currentTheta1 = 0.0;
float currentTheta2 = 0.0;
int gripperPos = 90;

void inverseKinematics(float x, float y) {
  float d = (x * x + y * y - j1 * j1 - j2 * j2) / (2.0 * j1 * j2);

  if (d < -1.0 || d > 1.0) {
    return;
  }

  currentX = x;
  currentY = y;

  float theta2 = -acos((pow(x, 2) + pow(y, 2) - pow(j1, 2) - pow(j2, 2)) / (2 * j1 * j2));
  float theta1 = atan2(y, x) - atan2(j2 * sin(theta2), j1 + j2 * cos(theta2));

  theta2 = theta2 * 180.0 / PI;
  theta1 = theta1 * 180.0 / PI;

  currentTheta1 = theta1;
  currentTheta2 = theta2;
}

long degreesToStepsJ1(float deg) {
  return (long)(deg / DEG_PER_STEP / GEAR_RATIO_J1);
}

long degreesToStepsJ2(float deg) {
  return (long)(deg / DEG_PER_STEP / GEAR_RATIO_J2);
}

long mmToSteps(float mm) {
  return (long)(mm * Z_STEPS_PER_MM);
}

float stepsToDegreesJ1(long steps) {
  return steps * DEG_PER_STEP * GEAR_RATIO_J1;
}

float stepsToDegreesJ2(long steps) {
  return steps * DEG_PER_STEP * GEAR_RATIO_J2;
}

void moveZ(float z_mm) {
  float carriageZ = z_mm + GRIPPER_LENGTH;
  stepperZ.moveTo(mmToSteps(carriageZ));
  currentZ = z_mm;
}

void moveXY(float x, float y) {
  inverseKinematics(x, y);
  stepperJ1.moveTo(degreesToStepsJ1(currentTheta1));
  stepperJ2.moveTo(degreesToStepsJ2(currentTheta2));
}

void moveTo(float x, float y, float z_mm) {
  moveZ(z_mm);
  moveXY(x, y);
}

void waitForMotors() {
  while (stepperZ.distanceToGo() != 0 ||
         stepperJ1.distanceToGo() != 0 ||
         stepperJ2.distanceToGo() != 0) {
    stepperZ.run();
    stepperJ1.run();
    stepperJ2.run();
  }
}

void openGripper() {
  gripper.write(0);
  gripperPos = 0;
  delay(500);
}

void closeGripper() {
  gripper.write(90);
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
  }
}

void setup() {
  Serial.begin(115200);

  stepperZ.setMaxSpeed(TODO);
  stepperZ.setAcceleration(TODO);

  stepperJ1.setMaxSpeed(TODO);
  stepperJ1.setAcceleration(TODO);

  stepperJ2.setMaxSpeed(TODO);
  stepperJ2.setAcceleration(TODO);
}

void loop() {
  parseSerial();
  stepperZ.run();
  stepperJ1.run();
  stepperJ2.run();
}
