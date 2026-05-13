"use client";

import { useEffect, useRef, useState } from "react";
import firstArmImage from "@/assets/arm/first_half.png";
import secondArmImage from "@/assets/arm/second_half.png";

export interface ArmMove {
  id: number;
  from: string;
  to: string;
  label: string;
  piece: string;
}

export type RobotArmMode = "idle" | "calibrating" | "playing";

interface Pose {
  x: number;
  y: number;
  lift: number;
  progress: number;
  holding: boolean;
  done: boolean;
}

export interface ArmDebugTarget {
  x: number;
  y: number;
}

export interface ArmAngles {
  a1: number;
  a2: number;
}

export const BASE = { x: 8.65+1, y: -0.65-1 };
const LINK_1 = 6.64;
const LINK_2 = 6.64;
const FIRST_ARM = {
  width: 556,
  height: 491,
  pivot: { x: 422, y: 130 },
  distal: { x: 88, y: 403 },
};
const SECOND_ARM = {
  width: 537,
  height: 619,
  pivot: { x: 426, y: 110 },
  distal: { x: 83, y: 536 },
};

function squareCenter(square: string) {
  const file = square.charCodeAt(0) - 97;
  const rank = Number(square[1]);
  return {
    x: file + 0.5,
    y: 8 - rank + 0.5,
  };
}

function ease(t: number) {
  return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
}

function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t;
}

function dist(a: { x: number; y: number }, b: { x: number; y: number }) {
  return Math.hypot(b.x - a.x, b.y - a.y);
}

function angleDeg(a: { x: number; y: number }, b: { x: number; y: number }) {
  return (Math.atan2(b.y - a.y, b.x - a.x) * 180) / Math.PI;
}

function imagePlacement(
  image: typeof FIRST_ARM,
  pivotWorld: { x: number; y: number },
  desiredDistalWorld: { x: number; y: number },
  linkLength: number
) {
  const scale = linkLength / dist(image.pivot, image.distal);
  const defaultAngle = angleDeg(image.pivot, image.distal);
  const desiredAngle = angleDeg(pivotWorld, desiredDistalWorld);
  return {
    x: pivotWorld.x - image.pivot.x * scale,
    y: pivotWorld.y - image.pivot.y * scale,
    width: image.width * scale,
    height: image.height * scale,
    rotation: desiredAngle - defaultAngle,
    pivotX: pivotWorld.x,
    pivotY: pivotWorld.y,
  };
}

function poseForMove(move: ArmMove, t: number): Pose {
  const from = squareCenter(move.from);
  const to = squareCenter(move.to);
  const phase = Math.min(0.999, t) * 5;
  const step = Math.floor(phase);
  const local = ease(phase - step);

  if (step === 0) {
    return { x: from.x, y: from.y, lift: lerp(1, 0, local), progress: t, holding: false, done: false };
  }
  if (step === 1) {
    return { x: from.x, y: from.y, lift: lerp(0, 1, local), progress: t, holding: true, done: false };
  }
  if (step === 2) {
    return { x: lerp(from.x, to.x, local), y: lerp(from.y, to.y, local), lift: 1, progress: t, holding: true, done: false };
  }
  if (step === 3) {
    return { x: to.x, y: to.y, lift: lerp(1, 0, local), progress: t, holding: true, done: false };
  }
  return { x: to.x, y: to.y, lift: lerp(0, 1, local), progress: t, holding: false, done: t >= 1 };
}

function poseForCalibration(t: number): Pose {
  const phase = Math.min(0.999, t) * 5;
  const step = Math.floor(phase);
  const local = ease(phase - step);

  if (step === 0) {
    // Arduino: Z axis goes down to the bottom switch, backs off, zeroes, then lifts.
    return { x: 7.2, y: 0.65, lift: local < 0.55 ? lerp(1, 0, local / 0.55) : lerp(0, 1, (local - 0.55) / 0.45), progress: t, holding: false, done: false };
  }

  if (step === 1) {
    // Arduino: J1 finds its single limit switch.
    return { x: lerp(7.2, 5.1, local), y: lerp(0.65, -0.05, local), lift: 1, progress: t, holding: false, done: false };
  }

  if (step === 2) {
    // Arduino: J1 moves away from the switch and declares IK zero.
    return { x: lerp(5.1, 7.35, local), y: lerp(-0.05, 0.85, local), lift: 1, progress: t, holding: false, done: false };
  }

  if (step === 3) {
    // Arduino: J2 sweeps from min switch toward max switch.
    return { x: lerp(7.35, 2.3, local), y: lerp(0.85, 3.65, local), lift: 1, progress: t, holding: false, done: false };
  }

  return {
    // Arduino: J2 returns to half range and declares zero.
    x: lerp(2.3, 7.5, local),
    y: lerp(3.65, 0.5, local),
    lift: 1,
    progress: t,
    holding: false,
    done: t >= 1,
  };
}

function inverseKinematics(target: { x: number; y: number }) {
  const dx = target.x - BASE.x;
  const dy = target.y - BASE.y;
  const d = Math.max(-1, Math.min(1, (dx * dx + dy * dy - LINK_1 * LINK_1 - LINK_2 * LINK_2) / (2 * LINK_1 * LINK_2)));
  const theta2 = -Math.acos(d);
  const theta1 = Math.atan2(dy, dx) - Math.atan2(LINK_2 * Math.sin(theta2), LINK_1 + LINK_2 * Math.cos(theta2));
  const joint = {
    x: BASE.x + LINK_1 * Math.cos(theta1),
    y: BASE.y + LINK_1 * Math.sin(theta1),
  };
  return {
    joint,
    theta1: (theta1 * 180) / Math.PI,
    theta2: (theta2 * 180) / Math.PI,
  };
}

function renderArmImages(
  target: { x: number; y: number },
  opacity: number,
  filter?: string
) {
  const ik = inverseKinematics(target);
  const firstPlacement = imagePlacement(FIRST_ARM, BASE, ik.joint, LINK_1);
  const secondPlacement = imagePlacement(SECOND_ARM, ik.joint, target, LINK_2);

  return (
    <g opacity={opacity} filter={filter}>
      <image
        href={secondArmImage.src}
        x={secondPlacement.x}
        y={secondPlacement.y}
        width={secondPlacement.width}
        height={secondPlacement.height}
        transform={`rotate(${secondPlacement.rotation} ${secondPlacement.pivotX} ${secondPlacement.pivotY})`}
        preserveAspectRatio="none"
      />
      <image
        href={firstArmImage.src}
        x={firstPlacement.x}
        y={firstPlacement.y}
        width={firstPlacement.width}
        height={firstPlacement.height}
        transform={`rotate(${firstPlacement.rotation} ${firstPlacement.pivotX} ${firstPlacement.pivotY})`}
        preserveAspectRatio="none"
      />
      <circle cx={BASE.x} cy={BASE.y} r="0.09" fill="white" stroke="oklch(0 0 0 / 0.45)" strokeWidth="0.025" opacity="0.55" />
    </g>
  );
}

export default function RobotArmOverlay({
  move,
  mode = move ? "playing" : "idle",
  onDone,
  debugTarget,
  opacity = 0.82,
  expectedOpacity = 0.28,
  onAnglesChange,
  embed = false,
}: {
  move: ArmMove | null;
  mode?: RobotArmMode;
  onDone?: (move: ArmMove) => void;
  debugTarget?: ArmDebugTarget | null;
  opacity?: number;
  expectedOpacity?: number;
  onAnglesChange?: (angles: ArmAngles) => void;
  embed?: boolean;
}) {
  const [pose, setPose] = useState<Pose>({ x: 4, y: 6, lift: 1, progress: 1, holding: false, done: true });
  const doneRef = useRef<number | null>(null);
  const onDoneRef = useRef(onDone);

  useEffect(() => {
    onDoneRef.current = onDone;
  }, [onDone]);

  useEffect(() => {
    if (debugTarget) {
      setPose({ x: debugTarget.x, y: debugTarget.y, lift: 1, progress: 1, holding: false, done: true });
      return;
    }
    if (!move && mode !== "calibrating") return;
    const started = performance.now();
    const duration = mode === "calibrating" ? 2600 : 2800;
    doneRef.current = null;
    let frame = 0;

    const tick = (now: number) => {
      const t = Math.min(1, (now - started) / duration);
      const next = mode === "calibrating" ? poseForCalibration(t) : poseForMove(move!, t);
      setPose(next);
      if (t < 1) {
        frame = requestAnimationFrame(tick);
        return;
      }
      if (move && doneRef.current !== move.id) {
        doneRef.current = move.id;
        window.setTimeout(() => onDoneRef.current?.(move), 120);
      }
    };

    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [debugTarget, mode, move]);

  const gripperY = pose.y - pose.lift * 0.55;
  const ik = inverseKinematics({ x: pose.x, y: gripperY });
  const expectedTarget = move ? squareCenter(move.to) : debugTarget;
  const cableTopY = Math.max(-0.85, gripperY - 0.75);
  const calibrating = mode === "calibrating";
  const zGaugeY = -0.72 + pose.lift * 0.42;

  useEffect(() => {
    onAnglesChange?.({ a1: ik.theta1, a2: ik.theta2 });
  }, [ik.theta1, ik.theta2, onAnglesChange]);

  const armContent = (
    <>
      <defs>
        <filter id="arm-shadow" x="-30%" y="-30%" width="160%" height="160%">
          <feDropShadow dx="0.04" dy="0.08" stdDeviation="0.08" floodOpacity="0.42" />
        </filter>
        <filter id="expected-arm-white">
          <feColorMatrix type="matrix" values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 1 0" />
        </filter>
      </defs>
      {calibrating && (
        <g opacity="0.95">
          <line x1="8.18" y1="-0.84" x2="8.18" y2="-0.28" stroke="var(--muted-foreground)" strokeWidth="0.035" />
          <rect x="8.05" y={zGaugeY} width="0.26" height="0.08" rx="0.02" fill="white" opacity="0.55" />
        </g>
      )}
      {expectedTarget && renderArmImages(expectedTarget, expectedOpacity, "url(#expected-arm-white)")}
      <g filter="url(#arm-shadow)">
        {renderArmImages({ x: pose.x, y: gripperY }, opacity)}
        <line x1={pose.x} y1={cableTopY} x2={pose.x} y2={gripperY + 0.18} stroke="oklch(0.85 0 0)" strokeWidth="0.055" strokeLinecap="round" />
        <path
          d={`M ${pose.x - 0.22} ${gripperY + 0.18} L ${pose.x - 0.08} ${gripperY + 0.38} M ${pose.x + 0.22} ${gripperY + 0.18} L ${pose.x + 0.08} ${gripperY + 0.38}`}
          stroke="oklch(0.85 0 0)"
          strokeWidth="0.06"
          strokeLinecap="round"
        />
      </g>
      {move && pose.holding && (
        <text
          x={pose.x}
          y={gripperY + 0.72}
          textAnchor="middle"
          dominantBaseline="middle"
          fontSize="0.72"
          fontFamily="serif"
          fill="black"
          stroke="white"
          strokeWidth="0.025"
          style={{ transform: `translate(${(pose.x - squareCenter(move.from).x) * 0.02}px, ${-pose.lift * 0.04}px)` }}
        >
          {move.piece}
        </text>
      )}
    </>
  );

  if (embed) {
    return <g>{armContent}</g>;
  }

  return (
    <svg
      viewBox="-1 -1 10 10"
      className="pointer-events-none absolute z-20 overflow-visible"
      style={{ left: "-12.5%", top: "-12.5%", width: "125%", height: "125%" }}
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      {armContent}
    </svg>
  );
}
