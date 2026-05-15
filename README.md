# ChArm — Chess-Playing SCARA Robot

ChArm is an autonomous chess-playing robot built around a two-link **SCARA arm**
with a vertical lead-screw Z axis. A human plays against a computer opponent on a
physical board: the robot watches the board through a camera, decides the
computer's reply with the Stockfish engine, and physically moves the piece with a
servo gripper.

This README is the master document for **rebuilding the project from scratch**.
For a function-by-function code walkthrough, see the sections below and the
inline docstrings in the source.

---

# 1. Project Overview

// Video

## What it does

1. The player picks a difficulty and starts a game from the on-robot LCD/encoder UI.
2. The player makes their move on the physical board and presses OK.
3. An **ESP32-CAM** photographs the board.
4. The **Python host** warps/rectifies the image, splits it into an 8×8 grid,
   detects per-square occupancy and piece colour, and infers which move the
   human made by comparing the observed board to all legal moves.
5. **Stockfish** computes the computer's reply at the selected skill level.
6. The host translates the move into Cartesian pick-and-place commands and sends
   them to the **Arduino Mega**, which drives the SCARA arm to physically move
   the piece (handling normal moves, captures, and castling).
7. Turn passes back to the human; repeat.

## 2. How to Build
### 2.1 Prerequisits
#### 3D Printer
// Why you need a 3d printer 

#### Laser Cutter
// Why you need a Laser cutter

#### Soldering Equipment
// Why you need soldering

### 2.2 Hardware (Bill of Materials)
// CAD build

### 2.3 Electronics & Wiring

All Arduino Mega pin assignments are defined in
[pins.h](arduino_code/src/hardware/src/pins.h):

**Steppers (CNC shield STEP/DIR + shared ENABLE)**

| Signal | Pin | Signal | Pin |
|--------|-----|--------|-----|
| X (J1) STEP | 2 | X (J1) DIR | 5 |
| Y (J2) STEP | 3 | Y (J2) DIR | 6 |
| Z STEP | 4 | Z DIR | 7 |
| Shared ENABLE | 8 | | |

**Limit switches** (INPUT_PULLUP, active-low)

| Switch | Pin |
|--------|-----|
| J1 (X) home | 9 |
| J2 (Y) home | 10 |
| Z bottom | 11 |

**Gripper servo:** pin 46

**Rotary encoder / button:** CLK 18, DT 19, SW 24

**16×2 LCD (4-bit mode):** RS 44, E 42, D4 38, D5 36, D6 34, D7 32

**ESP32-CAM ↔ Mega serial bridge** (UART, 9600 baud):

| ESP32-CAM | Mega |
|-----------|------|
| GPIO3 (RX) | Pin 18 / TX1 |
| GPIO1 (TX) | Pin 19 / RX1 |


### 2.4 Mechanical & numeric constants

All motion constants live in
[config.h](arduino_code/src/hardware/src/config.h). Re-measure and update these
for any rebuild:

- **Motor:** 200 steps/rev, 16 microsteps.
- **Gear ratios:** J1 = 20/160 driving/base teeth; J2 = 18/105 driving/joint teeth.
- **Link lengths:** Link 1 = 250 mm, Link 2 = 250 mm, Z travel ≈ 290 mm.
- **Lead screw:** 4 starts × 2 mm pitch = 8 mm lead → `STEPS_PER_MM` derived.
- **Gripper angles:** open 65°, closed 0°.
- **Pick/place Z presets** per piece type (`PICK_Z` / `PLACE_Z` arrays).

---

## 3. Software

### 3.1 Repository layout

```
2026sp-ChArm/
├── arduino_code/                  PlatformIO project — Arduino Mega firmware
│   ├── platformio.ini             Build environments
│   ├── src/
│   │   ├── main.cpp               Production firmware (entry point)
│   │   ├── main2.cpp              Z-limit-switch debug build
│   │   ├── main_*.cpp             Other test mains (LCD, UI, sim)
│   │   └── hardware/src/          Hardware abstraction classes
│   └── esp32_cam_mega_bridge/     ESP32-CAM + Mega bridge sketches
├── python_code/                   Python host program
│   ├── main.py                    End-to-end demo
│   ├── play_game.py               Game runner
│   ├── requirements.txt
│   ├── src/charm/                 The `charm` package
│   │   ├── vision/                Board calibration, occupancy/colour detection
│   │   ├── chess_engine/          Stockfish wrapper
│   │   ├── game/                  Orchestration + board state tracking
│   │   ├── arduino/               Serial bridges
│   │   └── utils/                 Bitmap helpers
│   └── tests/                     Unit tests + demos
├── inverse_kinematics/            Standalone IK sketches (reference)
├── Simulation/                    Arduino + Python simulation prototypes
├── cad/                           Mechanical design files
├── ChArm cable managment_bb.png   Wiring diagram
└── Proposal MIT.pdf               Original project proposal
```

### 3.2 Arduino firmware (`arduino_code/src/`)

**Top-level files**

- `main.cpp` — instantiates every hardware object as a global, runs `setup()` /
  `loop()`, and dispatches ASCII serial commands via `handleCommand()`. Supports
  a "controller mode" (`cm`) for live keyboard jogging.
- `main2.cpp` — minimal sketch that prints the Z-bottom limit switch state; built
  by the `debug_limit` env.
- `pins.h` / `config.h` — all pin numbers and all numeric constants.

**Hardware abstraction classes** (`hardware/src/`)

| Class / file | Responsibility |
|--------------|----------------|
| `StepperXYZ` | Thin STEP/DIR driver wrapper |
| `ScaraJoint` | Angle-aware joint: degrees ↔ steps, soft limits, residual tracking |
| `LeadScrew` | Same idea for the Z axis, in millimetres |
| `ScaraKinematics` | Pure-math forward/inverse kinematics for the two-link arm |
| `ScaraArm` | Combines two joints + kinematics → Cartesian `moveXY` |
| `Gripper` | Servo wrapper (open/close to configured angles) |
| `LimitSwitch` | INPUT_PULLUP switch wrapper |
| `limitAxis.h` | `findLimit` / `backOff` homing primitives |
| `ButtonInput` | Polled rotary encoder + push button |
| `LCDDisplay` | Flicker-free 16×2 LCD wrapper |
| `UIState` / `uiState.h` | All UI screens, menu state, LCD line generation |
| `UIController` | Glues encoder + LCD + host serial; runs the UI state machine |

> The encoder/LCD UI subsystem is wired up but its `begin()`/`loop()` calls in
> `main.cpp` may be commented out depending on the build — re-enable once the
> host-side protocol is in production.

**Arduino libraries used** (declared in `platformio.ini`)

- `arduino-libraries/Servo` — gripper servo control
- `Arduino-Libraries/LiquidCrystal` — 16×2 LCD

The ESP32-CAM sketch additionally uses `esp_camera`, `WiFi`, and `WebServer`
(part of the ESP32 Arduino core).

### 3.3 Python host (`python_code/src/charm/`)

| Module | Key contents |
|--------|--------------|
| `vision/` | Camera capture, two-stage perspective calibration, 8×8 grid split, occupancy + piece-colour detection, `pipeline.run_board_pipeline()` |
| `chess_engine/` | `best_move.get_best_move()` — Stockfish wrapper with configurable skill level |
| `game/` | `BoardStateTracker` (infers moves from observed bitmaps), `GameSession` (transcript), `GameController` (top-level orchestrator), `vision_integration` |
| `arduino/` | `arduino_bridge` (manual move serial, `execute_move()`), `uiController_bridge` (`ArduinoUIControllerLink`) |
| `utils/` | `bitmap.build_white_black_bitmaps()` — pivots colour results into the tracker's bitmap format |

**Vision pipeline at runtime:**

1. **Capture** — `transferphoto.fetch_raw_image()` downloads a JPEG from the
   ESP32-CAM (`http://<ip>/capture`).
2. **First warp** — project the four hand-picked outer corners to an 800×800
   square (`four_point_calibration.warp_from_calibration`).
3. **Inner refinement** — a second perspective transform using the inner-corner
   calibration so the board fills the frame exactly.
4. **Pipeline** — `pipeline.run_board_pipeline()` splits into 8×8 cells, runs
   occupancy (Canny edge density) and piece-colour (brightness) detection, and
   builds the white/black bitmaps.

Calibration JSON files (`board_calibration.json`, `inner_warp_calibration.json`)
are produced by the two `calibrate_*` scripts and consumed by the pipeline.

**Move inference:** `BoardStateTracker.update_from_bitmaps()` compares the
observed 8×8 bitmaps against the result of every legal move applied to the
current `chess.Board`, and accepts the unique best match. Statuses:
`accepted_legal_move`, `unchanged_position`, `invalid_observation`,
`ambiguous_observation`.

**Python libraries used** (`requirements.txt`)

| Package | Used for |
|---------|----------|
| `numpy<2` | Array math for vision |
| `opencv-python==4.9.0.80` | Image warping, masking, edge detection |
| `python-chess>=1.999` | Board representation, legal moves, UCI engine adapter |
| `stockfish` | Stockfish engine integration |
| `pyserial` | USB serial links to the Arduino |

### 3.4 How the two halves talk

**Manual move serial (`Serial`, 9600 baud)** — `arduino_bridge.execute_move()`
sends one ASCII line per step; the Arduino replies with one line (usually the new
position). Moves are blocking on the Arduino. Vocabulary: `moveXYZ x y z`,
`moveXY x y`, `moveZ mm`, `OG`/`CG` (open/close gripper), `calibrate`.

**UI controller serial (`Serial1`, 115200 baud)** — `ArduinoUIControllerLink`
runs a background reader thread. The Arduino is the source of truth for the
user-facing state.

| Direction | Messages |
|-----------|----------|
| Arduino → Host | `CHECK_BOARD`, `PLAYER_DONE`, `SET_DIFFICULTY n`, `CALIBRATE_START/DONE`, `BOARD_TIMEOUT`, `STATE …` |
| Host → Arduino | `BOARD_OK`/`BOARD_FAIL`, `BOT_THINKING`/`BOT_MOVING`, `PLAYER_TURN_WHITE/BLACK`, `MOVE_DONE`, `SET_MODE n`, `GET_STATE` |

**A full turn:** the human starts a game (`CHECK_BOARD` → host verifies the
starting position → `BOARD_OK`); the human moves a piece and presses OK
(`PLAYER_DONE`); the host runs vision, asks Stockfish, sends `BOT_MOVING`, then
streams `moveXYZ`/`OG`/`CG` commands over the manual serial to physically play
the move; finally it returns the turn with `PLAYER_TURN_*` + `MOVE_DONE`.

### 3.5 Pick-and-place logic (`arduino_bridge.execute_move`)

A UCI move is translated into a Cartesian command sequence:

- **Quiet move:** hover over source → down → close gripper → hover over
  destination → down → open → home.
- **Capture:** first carry the captured piece to the trash bin, then move the
  capturing piece.
- **Castling:** move the king, then the rook to its post-castle square (rook
  source/target hardcoded for `e1g1`, `e1c1`, `e8g8`, `e8c8`), then home.

Square-to-millimetre mapping is done by `coordinate_map.get_square_position()`
using `A1_X`, `A1_Y` and a per-square `STEP` (≈37.5 mm).