#include "scaraKinematics.h"

#include <math.h>

ScaraKinematics::ScaraKinematics(float j1, float j2) {
    this->j1 = j1;
    this->j2 = j2;
    this->currentX = 0.0f;
    this->currentY = 0.0f;
    this->currentTheta1 = 0.0f;
    this->currentTheta2 = 0.0f;
}

void ScaraKinematics::setLinks(float j1, float j2) {
    this->j1 = j1;
    this->j2 = j2;
}

void ScaraKinematics::inverseKinematics(float x, float y) {
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

void ScaraKinematics::forwardKinematics(float theta1Deg, float theta2Deg) {
    float t1 = theta1Deg * PI / 180.0f;
    float t2 = theta2Deg * PI / 180.0f;

    currentTheta1 = theta1Deg;
    currentTheta2 = theta2Deg;

    currentX = j1 * cos(t1) + j2 * cos(t1 + t2);
    currentY = j1 * sin(t1) + j2 * sin(t1 + t2);
}
