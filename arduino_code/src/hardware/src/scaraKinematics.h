#ifndef SCARA_KINEMATICS_H
#define SCARA_KINEMATICS_H

#include <Arduino.h>

// Planar 2-link SCARA inverse kinematics.
// j1, j2 are the link lengths in the same units as the target (x, y).
// The solved joint angles are stored in currentTheta1 / currentTheta2 (degrees).
class ScaraKinematics {
public:
    ScaraKinematics(float j1 = 0.0f, float j2 = 0.0f);

    void setLinks(float j1, float j2);

    // Solve for joint angles that place the end effector at (x, y).
    // If the target is out of reach the call is a no-op (state is unchanged).
    void inverseKinematics(float x, float y);

    float theta1() const { return currentTheta1; }
    float theta2() const { return currentTheta2; }
    float x() const { return currentX; }
    float y() const { return currentY; }

private:
    float j1;
    float j2;
    float currentX;
    float currentY;
    float currentTheta1;
    float currentTheta2;
};

#endif
