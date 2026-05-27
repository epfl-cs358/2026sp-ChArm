"use client";

import Link from "next/link";
import {
  Brain,
  Camera,
  ChevronRight,
  Eye,
  Gauge,
  SlidersHorizontal,
  Tags,
  Waypoints,
  Zap,
} from "lucide-react";

function Section({ id, icon: Icon, title, color, children }: {
  id: string;
  icon: React.ComponentType<{ className?: string; style?: React.CSSProperties }>;
  title: string;
  color: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="space-y-3 scroll-mt-6">
      <div className="flex items-center gap-3">
        <Icon className="size-5 shrink-0" style={{ color }} />
        <h2 className="font-jetbrains text-base font-semibold" style={{ color: "var(--charm-text)" }}>{title}</h2>
      </div>
      <div className="space-y-2 font-jetbrains text-xs leading-relaxed" style={{ color: "var(--charm-muted)" }}>
        {children}
      </div>
    </section>
  );
}

function Tip({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="rounded-md border px-3 py-2 font-jetbrains text-xs"
      style={{
        borderColor: "oklch(from var(--charm-cyan) l c h / 0.3)",
        background: "oklch(from var(--charm-cyan) l c h / 0.05)",
        color: "var(--charm-muted)",
      }}
    >
      <span style={{ color: "var(--charm-cyan)" }}>Tip · </span>{children}
    </div>
  );
}

function Step({ n, children }: { n: number; children: React.ReactNode }) {
  return (
    <div className="flex gap-3">
      <span
        className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full font-jetbrains text-[10px] font-semibold"
        style={{ background: "oklch(from var(--charm-cyan) l c h / 0.12)", color: "var(--charm-cyan)" }}
      >
        {n}
      </span>
      <p className="font-jetbrains text-xs leading-relaxed" style={{ color: "var(--charm-muted)" }}>{children}</p>
    </div>
  );
}

const TOC = [
  { id: "overview",        label: "System Overview" },
  { id: "vision-pipeline", label: "Vision Pipeline" },
  { id: "vision-settings", label: "Vision Settings" },
  { id: "labeling",        label: "Labeling Wizard" },
  { id: "cnn-wizard",      label: "CNN Wizard" },
  { id: "scara",           label: "SCARA Calibration" },
  { id: "serial",          label: "Serial Monitor" },
  { id: "first-game",      label: "Starting a Game" },
];

export default function GuidePage() {
  return (
    <div className="mx-auto max-w-3xl p-6 pb-24">
      {/* Header */}
      <div className="mb-8">
        <Link href="/" className="font-jetbrains text-xs underline" style={{ color: "var(--charm-muted)" }}>
          ← dashboard
        </Link>
        <h1 className="mt-3 font-jetbrains text-2xl font-semibold" style={{ color: "var(--charm-text)" }}>
          ChArm — Guide
        </h1>
        <p className="mt-1 font-jetbrains text-sm" style={{ color: "var(--charm-muted)" }}>
          How the webapp works, what each page does, and how to get a game running.
        </p>
      </div>

      <div className="flex gap-8">
        {/* TOC sidebar */}
        <nav className="hidden md:block w-44 shrink-0">
          <div className="sticky top-6 space-y-1">
            <p className="font-jetbrains text-[10px] uppercase tracking-widest mb-3" style={{ color: "var(--charm-muted)" }}>Contents</p>
            {TOC.map((item) => (
              <a
                key={item.id}
                href={`#${item.id}`}
                className="flex items-center gap-1.5 font-jetbrains text-xs py-1 hover:underline"
                style={{ color: "var(--charm-muted)" }}
              >
                <ChevronRight className="size-3 shrink-0" />
                {item.label}
              </a>
            ))}
          </div>
        </nav>

        {/* Content */}
        <div className="flex-1 space-y-10">

          <Section id="overview" icon={Gauge} title="System Overview" color="var(--charm-cyan)">
            <p>
              ChArm is a chess robot that sees the board with a camera, identifies piece positions, computes a move with Stockfish, and physically moves pieces with a SCARA robotic arm.
            </p>
            <p>
              The webapp is the control center. It lets you configure the vision pipeline, train and activate a CNN model, label training data, calibrate the robot arm, and monitor a live game.
            </p>
            <div className="grid grid-cols-2 gap-2 mt-3">
              {[
                { label: "Dashboard",       sub: "Game controls & live view", href: "/" },
                { label: "Vision Pipeline", sub: "Debug CV output",           href: "/lab" },
                { label: "Vision Settings", sub: "CV router & CNN config",    href: "/lab/vision-settings" },
                { label: "Labeling Wizard", sub: "Capture training data",     href: "/lab/labeling" },
                { label: "CNN Wizard",      sub: "Train & activate a model",  href: "/lab/cnn" },
                { label: "SCARA Calib.",    sub: "Teach the arm the board",   href: "/robot" },
              ].map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="rounded-md border px-3 py-2 hover:border-[oklch(from_var(--charm-cyan)_l_c_h_/_0.4)]"
                  style={{ borderColor: "var(--charm-border)", background: "var(--charm-card)" }}
                >
                  <p className="font-jetbrains text-xs font-semibold" style={{ color: "var(--charm-text)" }}>{item.label}</p>
                  <p className="font-jetbrains text-[10px]" style={{ color: "var(--charm-muted)" }}>{item.sub}</p>
                </Link>
              ))}
            </div>
          </Section>

          <Section id="vision-pipeline" icon={Eye} title="Vision Pipeline (/lab)" color="var(--charm-cyan)">
            <p>
              This page runs the classical computer vision pipeline on a captured image and shows debug output for every stage: raw capture, board edge detection, warp correction, occupancy scoring, and piece color classification.
            </p>
            <p>
              Use it to verify that the camera can see the board correctly and to fine-tune the <strong style={{ color: "var(--charm-text)" }}>Occupancy Threshold</strong> — the minimum score for a square to be considered occupied. Too low and empty squares trigger false positives; too high and faint pieces are missed.
            </p>
            <p>
              The <strong style={{ color: "var(--charm-text)" }}>Set Image Warp</strong> panel lets you drag the four board corners to fix perspective distortion. The <strong style={{ color: "var(--charm-text)" }}>ArUco calibration</strong> automates this if you have ArUco markers on the board frame.
            </p>
            <Tip>Run "Capture &amp; Run" after every physical camera adjustment to verify the pipeline still detects the board.</Tip>
          </Section>

          <Section id="vision-settings" icon={SlidersHorizontal} title="Vision Settings" color="var(--charm-cyan)">
            <p>
              Three sections control how the system sees:
            </p>
            <div className="space-y-2">
              <div className="rounded-md border px-3 py-2" style={{ borderColor: "var(--charm-border)" }}>
                <p className="font-semibold text-[11px] mb-0.5" style={{ color: "var(--charm-text)" }}>GENERAL CV — Pipeline Router</p>
                <p>Decides whether the classical <em>Vision</em> pipeline or the <em>CNN</em> neural net runs first on each board scan. The other acts as fallback. "Attempts per pipeline" controls how many retries each method gets before handing off.</p>
              </div>
              <div className="rounded-md border px-3 py-2" style={{ borderColor: "var(--charm-border)" }}>
                <p className="font-semibold text-[11px] mb-0.5" style={{ color: "var(--charm-text)" }}>VISION — Auto-save &amp; Advanced</p>
                <p>When <em>Auto-save validated frames</em> is on, every high-confidence scan saves 64 cell images to the training dataset — growing it automatically during games. The Advanced section exposes the Occupancy Threshold slider and a shortcut to warp calibration.</p>
              </div>
              <div className="rounded-md border px-3 py-2" style={{ borderColor: "var(--charm-border)" }}>
                <p className="font-semibold text-[11px] mb-0.5" style={{ color: "var(--charm-text)" }}>CNN — Active Model &amp; Dataset</p>
                <p>Shows all trained models and lets you activate one with a click. The active model is the one used for board scans. The Training Dataset name controls where auto-saved frames land.</p>
              </div>
            </div>
          </Section>

          <Section id="labeling" icon={Tags} title="Labeling Wizard (/lab/labeling)" color="var(--charm-cyan)">
            <p>
              Builds a labeled image dataset for CNN training. The arm moves a piece to every square while the camera takes photos, automatically generating labeled cell images (empty, white, black).
            </p>
            <div className="space-y-1.5">
              <Step n={1}>Setup — Name or load a dataset, pick the source square and piece type, set frames/square and settle delay.</Step>
              <Step n={2}>Calibration — Check that the camera sees the board cleanly before shooting.</Step>
              <Step n={3}>Empty board — Capture all 64 squares with no pieces for the "empty" class.</Step>
              <Step n={4}>White pieces — The arm sweeps the piece across every square; photos label each as "white".</Step>
              <Step n={5}>Black pieces — Same sweep with a black piece.</Step>
              <Step n={6}>Finish — Review accuracy statistics and optionally retake misclassified squares.</Step>
            </div>
            <Tip>Re-running the wizard with the same dataset name adds more data to the existing set rather than overwriting it.</Tip>
          </Section>

          <Section id="cnn-wizard" icon={Brain} title="CNN Wizard (/lab/cnn)" color="var(--charm-amber)">
            <p>
              Trains a convolutional neural network on your labeled dataset and lets you activate the resulting model for live game use.
            </p>
            <div className="space-y-1.5">
              <Step n={1}>Source — Choose the labeled dataset to train on.</Step>
              <Step n={2}>Build Dataset — Splits data into train/validation sets. You can rebuild with different settings at any time using the ↺ button.</Step>
              <Step n={3}>Train — Runs the training script. Watch accuracy improve per epoch in real time.</Step>
              <Step n={4}>Activate — Loads the trained model into memory so the game engine can use it.</Step>
              <Step n={5}>Live Test — Capture a board and see the CNN's predictions overlaid on the image.</Step>
            </div>
            <Tip>A model needs at least ~50–100 examples per class (empty/white/black) to be reliable. More data = better accuracy.</Tip>
          </Section>

          <Section id="scara" icon={Waypoints} title="SCARA Calibration (/robot)" color="var(--charm-muted)">
            <p>
              Teaches the robot arm where the chessboard squares are in physical space. You jog the arm to three known squares (a1, h1, h8) and save those positions. The firmware interpolates all 64 squares from those three reference points.
            </p>
            <p>
              You only need to redo this if the arm or board physically moves. The calibration is saved to disk and survives restarts.
            </p>
            <Tip>After any calibration change, click <strong style={{ color: "var(--charm-text)" }}>Arm calibration required</strong> on the dashboard to home the arm before starting a game.</Tip>
          </Section>

          <Section id="serial" icon={Zap} title="Serial Monitor (bottom bar)" color="var(--charm-muted)">
            <p>
              The <strong style={{ color: "var(--charm-text)" }}>Serial Monitor</strong> bar at the very bottom of the page shows every command sent to the Arduino arm controller (TX, in cyan) and every response received (RX, in amber) in real time.
            </p>
            <p>
              Click the bar to expand it. Use <em>pause</em> to freeze the log for inspection and <em>clear</em> to reset. This is useful for debugging arm movement issues or verifying that calibration commands are acknowledged.
            </p>
          </Section>

          <Section id="first-game" icon={Camera} title="Starting a Game — Checklist" color="var(--charm-cyan)">
            <div className="space-y-1.5">
              <Step n={1}>Set up the physical board in the starting position with white pieces on your side.</Step>
              <Step n={2}>Go to <Link href="/lab" className="underline" style={{ color: "var(--charm-cyan)" }}>Vision Pipeline</Link> and run "Capture &amp; Run" — verify that the board warp looks correct and piece count is 32.</Step>
              <Step n={3}>If pieces are mis-classified, you have two levers depending on which pipeline is active. If using the classical pipeline, adjust the <strong style={{ color: "var(--charm-text)" }}>Occupancy Threshold</strong> in <Link href="/lab/vision-settings" className="underline" style={{ color: "var(--charm-cyan)" }}>Vision Settings → Vision → Advanced</Link>. If relying on the CNN, try activating a different model in <Link href="/lab/vision-settings" className="underline" style={{ color: "var(--charm-cyan)" }}>Vision Settings → CNN → Active Model</Link> — a model trained on more data or a different lighting condition may perform better.</Step>
              <Step n={4}>Back on the Dashboard, click <strong style={{ color: "var(--charm-text)" }}>Arm calibration required</strong> and wait for the arm to home.</Step>
              <Step n={5}>Choose your difficulty with the Stockfish level button.</Step>
              <Step n={6}>Click <strong style={{ color: "var(--charm-text)" }}>Start game</strong>, pick your color, and make your first move. When done, click <strong style={{ color: "var(--charm-text)" }}>Player done</strong> to trigger the CV scan and robot reply.</Step>
            </div>
            <Tip>If the LCD controller box is connected, use <strong style={{ color: "var(--charm-text)" }}>Run LCD</strong> to sync the physical buttons with the webapp — both can drive the same game simultaneously.</Tip>
          </Section>

        </div>
      </div>
    </div>
  );
}
