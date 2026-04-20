#ifndef SCARA_KINEMATICS_H
#define SCARA_KINEMATICS_H

#include <Arduino.h>

// ScaraArm owns and stores these
struct IKResult {
    float theta1; // degrees
    float theta2; // degrees
    bool  reachable;
};
 
struct FKResult {
    float x; // mm
    float y; // mm
};

// Planar 2-link SCARA inverse kinematics.
// j1, j2 are the link lengths in the same units as the target (x, y).
// The solved joint angles are stored in currentTheta1 / currentTheta2 (degrees).
class ScaraKinematics {
public:
    ScaraKinematics(float j1 = 0.0f, float j2 = 0.0f);

    void setLinks(float j1, float j2);

    // Solve for joint angles that place the end effector at (x, y).
    // If the target is out of reach the call is a no-op (state is unchanged).
    IKResult inverseKinematics(float x, float y);
    // Calculate where the end effector actually is
    FKResult forwardKinematics(float theta1Deg, float theta2Deg);

private:
    float j1;
    float j2;
};

#endif
