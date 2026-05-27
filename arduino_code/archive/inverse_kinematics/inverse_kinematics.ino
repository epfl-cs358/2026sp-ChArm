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

const int DirZ = 7;
const int DirY = 6;
const int DirX = 5;
const int StepZ = 4;
const int StepY = 3;
const int StepX = 2;

const int EnablePin = 8;   // ENABLE (LOW = ON)

// speed tuning for Y / Z (bit-banged)
unsigned int pulseDelay = 1500;   // microseconds HIGH

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

  if (carriageZ > j3)
    return;

  long stepsZ = mmToSteps(carriageZ);

  Serial.print("Moving Z ");
  Serial.print(stepsZ);
  Serial.println(" steps");

  long countZ = labs(stepsZ);

  if (stepsZ > 0) digitalWrite(DirZ, HIGH);
  else           digitalWrite(DirZ, LOW);

  Serial.print("Z count is");
  Serial.println(countZ);

  for (long i = 0; i < countZ; i++) {
    digitalWrite(StepZ, HIGH);
    delayMicroseconds(pulseDelay);
    digitalWrite(StepZ, LOW);
    delayMicroseconds(pulseDelay);
  }

  currentZ = z_mm;
}

void moveXY(float x, float y) {
  inverseKinematics(x, y);

  long stepsJ1 = degreesToStepsJ1(currentTheta1);
  long stepsJ2 = degreesToStepsJ1(currentTheta2);

  Serial.print("Moving X ");
  Serial.print(stepsJ1);
  Serial.println(" steps");

  Serial.print("Moving Y ");
  Serial.print(stepsJ2);
  Serial.println(" steps");

  long countJ1 = labs(stepsJ1);
  long countJ2 = labs(stepsJ2);

  if (stepsJ1 > 0) digitalWrite(DirX, LOW);
  else           digitalWrite(DirX, HIGH);

  if (stepsJ2 > 0) digitalWrite(DirY, LOW);
  else           digitalWrite(DirY, HIGH);

  Serial.print("X Count is");
  Serial.println(countJ1);

  Serial.print("Y Count is");
  Serial.println(countJ2);

  for (long i = 0; i < countJ1; i++) {
    digitalWrite(StepX, HIGH);
    delayMicroseconds(pulseDelay);
    digitalWrite(StepX, LOW);
    delayMicroseconds(pulseDelay);
  }

  for (long i = 0; i < countJ2; i++) {
    digitalWrite(StepY, HIGH);
    delayMicroseconds(pulseDelay);
    digitalWrite(StepY, LOW);
    delayMicroseconds(pulseDelay);
  }
}

void moveTo(float x, float y, float z_mm) {
  if (currentZ != z_mm){
    moveZ(z_mm);
  } 

  if (currentX != x || currentY != y){
    moveXY(x, y);
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
  
  } else if (cmd == "OG") {
    openGripper();

  } else if (cmd == "CG") {
    closeGripper();
  }
}

void setup() {
  Serial.begin(115200);

  pinMode(StepX, OUTPUT);
  pinMode(DirX,  OUTPUT);

  pinMode(StepY, OUTPUT);
  pinMode(DirY,  OUTPUT);

  pinMode(StepZ, OUTPUT);
  pinMode(DirZ,  OUTPUT);

  pinMode(EnablePin, OUTPUT);
  digitalWrite(EnablePin, LOW);

  Serial.println("ready");
}

void loop() {
  parseSerial();
}


