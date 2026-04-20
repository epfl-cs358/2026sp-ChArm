#include "scaraKinematics.h"

#include <math.h>

ScaraKinematics::ScaraKinematics(float j1, float j2) {
    this->j1 = j1;
    this->j2 = j2;
}

void ScaraKinematics::setLinks(float j1, float j2) {
    this->j1 = j1;
    this->j2 = j2;
}

IKResult ScaraKinematics::inverseKinematics(float x, float y) {
    float d = (x * x + y * y - j1 * j1 - j2 * j2) / (2.0 * j1 * j2);

    if (d < -1.0 || d > 1.0) {
        return {0.0f, 0.0f, false};
    }

    float theta2 = -acos(d);
    float theta1 = atan2(y, x) - atan2(j2 * sin(theta2), j1 + j2 * cos(theta2));

    return {
        theta1 * 180.0f / PI,
        theta2 * 180.0f / PI,
        true
    };
}

FKResult ScaraKinematics::forwardKinematics(float theta1Deg, float theta2Deg) {
    float t1 = theta1Deg * PI / 180.0f;
    float t2 = theta2Deg * PI / 180.0f;

    return {
        j1 * cos(t1) + j2 * cos(t1 + t2),
        j1 * sin(t1) + j2 * sin(t1 + t2)
    };
}
