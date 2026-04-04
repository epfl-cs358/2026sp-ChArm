#include <AccelStepper.h>
#include <Servo.h>

#define MICROSTEP 16
#define STEPS_PER_REV (200 * MICROSTEP)
#define DEG_PER_STEP (360.0 / STEPS_PER_REV)  // motor shaft: 0.1125° per step
#define Z_STEPS_PER_MM 8

// ── Gear ratios ───────────────────────────────────────────────
// RECHECK: driving pulley teeth = 100 (assumed, needs verification)
// Joint pulley = 105 teeth, Base pulley = 160 teeth
#define DRIVING_TEETH  100    // TODO: recheck this value
#define JOINT_TEETH    105
#define BASE_TEETH     160

// gear_ratio = driving / driven
// joint turns LESS than motor (gear_ratio < 1 = reduction)
#define GEAR_RATIO_J1  ((float)DRIVING_TEETH / JOINT_TEETH)   // 0.952
#define GEAR_RATIO_J2  ((float)DRIVING_TEETH / JOINT_TEETH)   // 0.952
#define GEAR_RATIO_Z   ((float)DRIVING_TEETH / BASE_TEETH)    // 0.625

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

AccelStepper stepperZ (motorInterfaceType, stepPinX, dirPinX);
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
    Serial.println("ERROR: Target out of reach!");
    return;
  }

  currentX = x;
  currentY = y;

  float theta2 = -acos((pow(x, 2) + pow(y, 2) - pow(j1, 2) - pow(j2, 2)) / (2*j1*j2));
  float theta1 = atan2(y, x) - atan2(j2 * sin(theta2), j1 + j2 * cos(theta2));

  theta2 = theta2 * 180.0 / PI;
  theta1 = theta1 * 180.0 / PI;

  currentTheta1 = theta1;
  currentTheta2 = theta2;

  Serial.print("THETA1:"); Serial.println(currentTheta1, 4);
  Serial.print("THETA2:"); Serial.println(currentTheta2, 4);
}

// ── Steps conversion WITH gear ratio ─────────────────────────
// Joint needs to turn deg degrees
// Motor must turn deg / GEAR_RATIO degrees to achieve that
// Because motor is the driving side: more motor turns → less joint turns
long degreesToStepsJ1(float deg) {
  return (long)(deg / DEG_PER_STEP / GEAR_RATIO_J1);
}

long degreesToStepsJ2(float deg) {
  return (long)(deg / DEG_PER_STEP / GEAR_RATIO_J2);
}

long mmToSteps(float mm) {
  return (long)(mm * Z_STEPS_PER_MM);
}

// Convert motor steps back to joint degrees (for live streaming)
float stepsToDegreesJ1(long steps) {
  return steps * DEG_PER_STEP * GEAR_RATIO_J1;
}

float stepsToDegreesJ2(long steps) {
  return steps * DEG_PER_STEP * GEAR_RATIO_J2;
}
// ─────────────────────────────────────────────────────────────

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
  unsigned long lastPrint = 0;

  while (stepperZ.distanceToGo()  != 0 ||
         stepperJ1.distanceToGo() != 0 ||
         stepperJ2.distanceToGo() != 0) {
    stepperZ.run();
    stepperJ1.run();
    stepperJ2.run();

    unsigned long now = millis();
    if (now - lastPrint >= 20) {
      // Convert motor steps back to joint degrees
      float t1now = stepsToDegreesJ1(stepperJ1.currentPosition());
      float t2now = stepsToDegreesJ2(stepperJ2.currentPosition());
      float znow  = (float)stepperZ.currentPosition() / Z_STEPS_PER_MM - GRIPPER_LENGTH;

      Serial.print("POS T1:"); Serial.print(t1now, 2);
      Serial.print(" T2:");    Serial.print(t2now, 2);
      Serial.print(" Z:");     Serial.println(znow, 2);

      lastPrint = now;
    }
  }

  Serial.println("DONE");
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

    long prevJ1 = stepperJ1.currentPosition();
    long prevJ2 = stepperJ2.currentPosition();
    long prevZ  = stepperZ.currentPosition();

    moveTo(x, y, z);
    waitForMotors();

    // ── Relative rotation ──────────────────────────────────────
    long deltaJ1 = stepperJ1.currentPosition() - prevJ1;
    long deltaJ2 = stepperJ2.currentPosition() - prevJ2;
    long deltaZ  = stepperZ.currentPosition()  - prevZ;

    // Motor revolutions
    float motorRevsJ1 = (float)deltaJ1 / STEPS_PER_REV;
    float motorRevsJ2 = (float)deltaJ2 / STEPS_PER_REV;
    float motorRevsZ  = (float)deltaZ  / STEPS_PER_REV;

    // Joint revolutions = motor_revs × gear_ratio
    float jointRevsJ1 = motorRevsJ1 * GEAR_RATIO_J1;
    float jointRevsJ2 = motorRevsJ2 * GEAR_RATIO_J2;
    float jointRevsZ  = motorRevsZ  * GEAR_RATIO_Z;

    Serial.print("DELTA");
    Serial.print(" motorJ1:"); Serial.print(motorRevsJ1, 4);
    Serial.print(" motorJ2:"); Serial.print(motorRevsJ2, 4);
    Serial.print(" motorZ:");  Serial.print(motorRevsZ,  4);
    Serial.print(" jointJ1:"); Serial.print(jointRevsJ1, 4);
    Serial.print(" jointJ2:"); Serial.print(jointRevsJ2, 4);
    Serial.print(" jointZ:");  Serial.println(jointRevsZ,  4);
    // ──────────────────────────────────────────────────────────

  } else if (cmd == "OG") {
    openGripper();
  } else if (cmd == "CG") {
    closeGripper();
  } else {
    Serial.println("Unknown command.");
  }
}

void setup() {
  Serial.begin(115200);

  stepperZ.setMaxSpeed(500);
  stepperZ.setAcceleration(200);
  stepperJ1.setMaxSpeed(500);
  stepperJ1.setAcceleration(200);
  stepperJ2.setMaxSpeed(500);
  stepperJ2.setAcceleration(200);
}

void loop() {
  parseSerial();
  stepperZ.run();
  stepperJ1.run();
  stepperJ2.run();
}
