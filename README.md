# ChArm — Chess-Playing SCARA Robot

ChArm is a chess-playing robot built around a two-link SCARA arm with a vertical
lead-screw Z axis, a servo gripper, an Arduino-controlled UI, and a Python host
that handles computer vision and chess logic.

//TODO Add picture/Video

The intended workflow is:

1. The player picks a difficulty and starts a game from the on-robot LCD/encoder UI.
2. The player makes their move on the physical board and presses OK.
3. An ESP32-CAM captures the board.
4. The Python host warps/rectifies the image, splits it into an 8×8 grid, detects per-square occupancy and piece colour, and infers which move the human made by comparing the observed board to all legal moves.
5. Stockfish computes the computer's reply at the selected skill level.
6. The host translates the move into Cartesian pick-and-place commands and sends them to the Arduino Mega, which drives the SCARA arm to physically move the piece (handling normal moves, captures, and castling).
7. Turn passes back to the human; repeat.

This README is the top-level guide for understanding, rebuilding, and running
the project.

## Project Overview

ChArm combines four subsystems:

- **mechanics**: SCARA arm, Z lead screw, servo gripper, custom board setup
- **embedded control**: Arduino Mega firmware for homing, motion, calibration, and UI
- **computer vision**: board rectification, 8×8 cell extraction, occupancy and colour detection
- **game logic**: `python-chess` state tracking and Stockfish move selection

The project is organized so that hardware control and chess/vision logic can be
developed and tested independently.

## Main Features

- Detects the board state from a calibrated camera image
- Converts the observed board into white/black 8×8 occupancy bitmaps
- Reconstructs the played move by comparing the observation against all legal moves
- Validates whether an observed update is legal, invalid, unchanged, or ambiguous
- Uses Stockfish to compute the robot's move
- Sends blocking pick-and-place commands to the Arduino Mega
- Supports captures, castling, and vision-driven game progression

## Repository Layout

```text
2026sp-ChArm/
├── arduino_code/                 PlatformIO project for the Arduino Mega
│   ├── src/                      Firmware entry points and hardware classes
│   ├── esp32_cam_mega_bridge/    ESP32-CAM ↔ Mega bridge sketches
│   └── esp32_ui_box/             ESP32 UI box firmware
├── python_code/                  Python host-side code
│   ├── src/charm/
│   │   ├── vision/               Board calibration and image processing
│   │   ├── chess_engine/         Stockfish integration
│   │   ├── game/                 Board state tracking and orchestration
│   │   ├── arduino/              Serial and UI bridges
│   │   └── utils/                Shared helpers
│   ├── tests/                    Unit tests and demos
│   ├── play_game.py              Full game entry point
│   ├── main.py                   Vision / integration runner
│   └── capture_game_session.py   Raw image capture helper
├── inverse_kinematics/           Early standalone SCARA sketches
├── Simulation/                   Prototyping / simulation files
├── webapp/                       Optional Next.js frontend
├── webapp_backend/               Optional FastAPI backend
├── Proposal MIT.pdf              Original project proposal
└── notes.md                      Project notes and ideas
```

## Hardware Summary

The physical system is centered around:

- **Arduino Mega 2560**
- **Two SCARA rotational joints**
- **One Z-axis lead screw**
- **Servo gripper**
- **Limit switches**
- **ESP32-CAM** for board capture
- **ESP32D-WIFI** for the player-facing LCD/button interface
- **16×2 LCD + rotary encoder/button**
- **Stepper drivers on a CNC-shield-like STEP/DIR setup**

### Fabrication Tools

You will likely need:

- **3D printer** for mechanical arm parts, brackets, gripper components, and enclosures
- **laser cutter** for flat structural parts such as board elements, panels, or mounts
- **soldering equipment** for wiring, connectors, switch integration, and board-level assembly

### CAD Overview
// TODO
// Add CAD files
// Add Building instruction

### Electronics and Wiring

//TODO Add Electrical Circuit picture and explanation

The main production firmware pin assignments are defined in
[arduino_code/src/hardware/src/pins.h](arduino_code/src/hardware/src/pins.h).

**Steppers (STEP / DIR / shared ENABLE)**

| Signal | Pin | Signal | Pin |
|---|---:|---|---:|
| X / J1 STEP | 2 | X / J1 DIR | 5 |
| Y / J2 STEP | 3 | Y / J2 DIR | 6 |
| Z STEP | 4 | Z DIR | 7 |
| ENABLE | 8 |  |  |

**Limit switches**

| Switch | Pin |
|---|---:|
| J1 home | 9 |
| J2 home | 10 |
| Z bottom | 11 |

**Other I/O**

- Gripper servo: pin `46`

### Motion Constants

The motion and geometry constants live in
[arduino_code/src/hardware/src/config.h](arduino_code/src/hardware/src/config.h).
These values should be checked whenever the robot is rebuilt or recalibrated.

Important examples:

- motor steps/rev and microstepping
- SCARA gear ratios
- link lengths
- lead screw conversion to `STEPS_PER_MM`
- gripper open/close angles
- pick/place Z presets

## Software Architecture

### Arduino Side

The main Arduino entry point is
[arduino_code/src/main.cpp](arduino_code/src/main.cpp).

It is responsible for:

- setting up steppers, joints, gripper, lead screw, and limit switches
- handling calibration and EEPROM persistence
- receiving serial commands
- translating high-level movement requests into robot motion

Key hardware abstractions are in `arduino_code/src/hardware/src/`:

- `StepperXYZ`
- `ScaraJoint`
- `LeadScrew`
- `ScaraKinematics`
- `ScaraArm`
- `Gripper`
- `LimitSwitch`

The PlatformIO environments are defined in
[arduino_code/platformio.ini](arduino_code/platformio.ini).

### ESP32-Cam Side

The ESP32-CAM firmware is in
[arduino_code/esp32_cam_mega_bridge/esp32_cam_code_mit.ino](arduino_code/esp32_cam_mega_bridge/esp32_cam_code_mit.ino).

Upload it to an AI Thinker ESP32-CAM board with the Arduino ESP32 core. Before
flashing, set the `ssid` and `password` constants in the sketch to the Wi-Fi
network used by the Python host.

At runtime, the board:

- connects to Wi-Fi and starts an HTTP server on port `80`
- exposes `/capture` as a JPEG image endpoint for browser or Python capture
- exposes `/status` as a small JSON health endpoint
- listens to the Arduino Mega over UART at `9600` baud

The Mega bridge uses these serial commands:

| Command | Response |
|---|---|
| `STATUS` | `ESP32_OK` |
| `IP` | `IP <address>` |
| `CAPTURE` | `CAPTURE_OK` or `CAPTURE_FAIL` |

Wire the bridge serial connection as documented in the sketch:

| ESP32-CAM | Arduino Mega |
|---|---|
| GPIO3 / TX | pin 19 / RX1 |
| GPIO1 / RX | pin 18 / TX1 |

### ESP32D Side

The ESP32D firmware for the player-facing UI box is in
[arduino_code/esp32_ui_box/](arduino_code/esp32_ui_box/).

Before flashing, edit `WIFI_CREDENTIALS` in
[arduino_code/esp32_ui_box/esp32_ui_box.cpp](arduino_code/esp32_ui_box/esp32_ui_box.cpp)
so the ESP32 can join the same Wi-Fi network as the Python host. If no
configured network is reachable, the firmware starts a fallback access point:

- SSID: `ChArm-UI`
- password: `charm1234`

Build and upload with PlatformIO:

```bash
cd arduino_code/esp32_ui_box
pio run -e esp32_ui_box -t upload
pio device monitor -e esp32_ui_box
```

The firmware starts a TCP server on port `8765`. The LCD shows the ESP32 IP
address after Wi-Fi connects; pass that address to the Python host with
`--esp32-host`.

Wire the rotary encoder/button and LCD to the ESP32D pins defined in
[arduino_code/src/hardware/src/pins.h](arduino_code/src/hardware/src/pins.h):

| UI signal | ESP32D pin |
|---|---:|
| Encoder SW | 5 |
| Encoder DT | 17 |
| Encoder CLK | 16 |
| LCD RS | 14 |
| LCD E | 27 |
| LCD D4 | 26 |
| LCD D5 | 25 |
| LCD D6 | 33 |
| LCD D7 | 32 |

The UI box exchanges newline-terminated TCP commands with Python. The main
ESP32-to-Python commands are `CHECK_BOARD`, `PLAYER_DONE`, `SET_COLOR <n>`,
`SET_DIFFICULTY <n>`, and `CALIBRATION`. Python replies with status updates
such as `BOARD_OK`, `BOARD_FAIL`, `BOT_THINKING`, `BOT_MOVING`,
`PLAYER_TURN_WHITE`, `PLAYER_TURN_BLACK`, `MOVE_DONE`, and `GAME_OVER <reason>`.

### Python Side

The Python package lives in `python_code/src/charm/`.

#### `vision/`

The vision pipeline performs:

- board corner calibration
- perspective rectification
- splitting the image into 64 cells
- occupancy detection
- piece-colour detection
- construction of white/black bitmaps

Important files:

- `pipeline.py`
- `board_detector.py`
- `grid_splitter.py`
- `occupancy_detector.py`
- `piece_color_detector.py`
- `four_point_calibration.py`
- `calibrated_pipeline.py`

### Vision & CNN Architecture

This section describes the technical structure of the board-recognition stack,
including both the geometric preprocessing pipeline and the planned CNN-based
classifier architecture.

#### Geometric Vision Pipeline

The geometric pipeline transforms a raw, perspective-distorted camera image into
a normalized 8×8 board representation.

**Two-stage perspective warping**

To align the board as accurately as possible, the system applies two sequential
homography transformations:

1. **Global warp**  
   The four outer corners of the board, obtained through calibration, are
   mapped to an initial 800×800 square image.

2. **Inner refinement**  
   Internal grid intersections are then used to refine the first warp. This
   compensates for lens distortion or small geometric imperfections, producing a
   final board image where each square is aligned consistently.

**Grid splitting**

The refined image is divided into 64 `SquareCell` objects. Each cell contains:

- an RGB crop of one board square
- its row and column indices within the 8×8 grid

#### CNN Classification

The CNN classifier is intended to replace or complement the classical
occupancy/brightness heuristics with a learned model trained specifically on the
ChArm board and piece set.

**Model objective**

The classifier predicts one of three classes for each square:

- `empty`
- `white`
- `black`

**Model structure**

A lightweight Keras CNN is planned for efficient inference on CPU:

- input: normalized RGB square image
- three convolutional blocks with increasing filter counts
- max-pooling for spatial downsampling
- global average pooling for robustness to slight piece offsets
- softmax output over the three classes

**Batch inference**

Instead of processing cells individually, all 64 board squares can be stacked
into a single tensor and passed through the model in one forward pass. This
allows the whole board to be evaluated efficiently and consistently.

#### Fail-Safe Mechanism

To improve robustness in difficult conditions such as shadows, blur, or unclear
piece placement, the vision system is designed around a retry-and-fallback
strategy.

**Primary / fallback routing**

A routing layer can attempt multiple captures and evaluate them in sequence:

1. first attempts use the CNN-based pipeline
2. if repeated captures still fail to produce a valid board update, the system
   falls back to the classical pipeline
3. only observations that can be matched to a valid board-state transition are
   accepted

**Validation rule**

An observation is only accepted if the `BoardStateTracker` can interpret it as:

- a unique legal move
- or a valid unchanged board state

If the result is invalid or ambiguous, the frame is rejected and a new capture
is requested.

#### Living Dataset and Continuous Improvement

A major long-term advantage of the CNN approach is that the model can improve
over time using data collected during real operation.

**Correction loop**

When a square is misclassified:

1. the user corrects the label through the interface
2. the corresponding cell image is stored in the dataset
3. the next training cycle includes this new example

**Environmental specialization**

Over time, the model becomes more specialized to:

- the exact ChArm board texture
- the real lighting conditions
- the specific physical pieces
- real camera noise and shadows

This creates a system that becomes more robust with use, instead of relying
only on fixed handcrafted thresholds.

#### `game/`

This module handles chess-state reconstruction and game orchestration.

Important files:

- `state_tracker.py`
- `vision_integration.py`
- `game_session.py`
- `game_controller.py`

What they do:

- `BoardStateTracker` keeps the current `python-chess` board state
- `state_tracker.py` infers the best legal move from observed bitmaps
- `vision_integration.py` connects the vision output to the tracker
- `GameSession` manages initialization, player move detection, and robot move verification
- `GameController` coordinates UI events, image capture, Stockfish, and robot motion

#### `chess_engine/`

- `best_move.py` wraps Stockfish and returns the engine move for a given board

#### `arduino/`

- `arduino_bridge.py` sends movement commands to the Arduino Mega
- `uiController_bridge.py` communicates with the ESP32-based UI

## How the Game Flow Works

At a high level:

1. `play_game.py` starts the Python host process.
2. The host connects to:
   - the **ESP32 UI box** over TCP
   - the **Arduino Mega** over USB serial
3. The user starts the game from the UI.
4. The host validates the initial board from a calibrated image.
5. After each player move, the host:
   - captures a new board image,
   - runs the vision pipeline,
   - reconstructs the move with `python-chess`,
   - validates whether the observation is acceptable.
6. Stockfish computes the robot response.
7. The Arduino executes the robot move physically.

The tracker statuses currently used by the move-validity layer are:

- `accepted_legal_move`
- `unchanged_position`
- `invalid_observation`
- `ambiguous_observation`

## Setup

### Python Environment

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r python_code/requirements.txt
```

Install Stockfish separately if it is not already available on your machine:

```bash
brew install stockfish
```

or on Debian/Ubuntu:

```bash
sudo apt install stockfish
```

### Arduino Firmware

The production firmware is built from `arduino_code/` with PlatformIO.

Typical workflow:

```bash
cd arduino_code
pio run
pio run --target upload
pio device monitor
```

### Optional Web Tools

The repository also contains:

- `webapp/` — Next.js frontend
- `webapp_backend/` — FastAPI backend

These are optional developer tools and are not required to run the core robot
pipeline.

## Calibration

The Python vision stack expects calibration JSON files:

- `python_code/board_calibration.json`
- `python_code/inner_warp_calibration.json`

Calibration-related scripts live in:

- `python_code/src/charm/vision/calibrate_board_corners.py`
- `python_code/src/charm/vision/calibrate_inner_warp_corners.py`
- `python_code/src/charm/vision/run_two_step_calibration.py`
- `python_code/manual_calibration_interactive.py`

The typical workflow is:

1. capture or load a board image,
2. calibrate the outer board corners,
3. calibrate the inner warp / refined board area,
4. save both calibration files,
5. use those files when running the game pipeline.

## Common Workflows

### 1. Run the vision pipeline on a test image

```bash
source .venv/bin/activate
python python_code/main.py
```

This:

- loads a test image,
- runs the board pipeline,
- prints occupancy and bitmaps,
- saves debug images such as:
  - `output_black_mask_debug.jpg`
  - `output_grid_debug.jpg`
  - `output_piece_color_debug.jpg`

### 2. Run the full host-side game application

```bash
source .venv/bin/activate
python python_code/play_game.py \
  --esp32-host 172.21.71.52 \
  --engine-path stockfish
```

Useful arguments:

| Argument | Description |
|---|---|
| `--esp32-host` | IP address of the ESP32 UI box |
| `--esp32-port` | TCP port for the UI box |
| `--arm-port` | Serial port of the Arduino Mega |
| `--player-color` | Initial fallback player colour |
| `--difficulty` | `0=easy`, `1=medium`, `2=hard` |
| `--board-calibration` | Outer board calibration JSON |
| `--inner-calibration` | Inner warp calibration JSON |
| `--engine-path` | Stockfish binary path |
| `--think-time` | Stockfish think time in seconds |

### 3. Capture a sequence of raw board photos

```bash
source .venv/bin/activate
python python_code/capture_game_session.py --game game_2
```

This is useful for collecting images to debug or improve the vision pipeline.

### 4. Test the state tracker without camera input

```bash
source .venv/bin/activate
python python_code/tests/demo_state_tracker.py --moves e2e4 e7e5 g1f3
```

This demo:

- builds a known chess position,
- converts it into white/black bitmaps,
- asks the tracker to infer the last move,
- prints the resulting tracker status and board state.

You can also demonstrate noisy or invalid observations:

```bash
python python_code/tests/demo_state_tracker.py --moves e2e4 --inject-noise --max-mismatches 1
python python_code/tests/demo_state_tracker.py --moves e2e4 --show-invalid-example
```

## Testing

Run the Python test suite:

```bash
source .venv/bin/activate
python -m unittest discover -s python_code/tests -v
```

The current tests cover:

- board-to-bitmap conversion
- move reconstruction from observed bitmaps
- captures, castling, en passant, and promotion behaviour
- sequential board updates
- noisy accepted observations
- invalid rejected observations

## Current Limitations

- The move tracker currently works from **occupancy + piece colour**, not full piece identity.
- Because of that, the system relies on a **known previous chess position** and infers the move by iterating over legal moves.
- Promotion cannot be uniquely identified from occupancy/colour alone if multiple promotion pieces would produce the same bitmap pattern.
- Real-world robustness still depends on lighting, calibration quality, and board visibility.
- //TODO review as a team

## Future Improvements

Some realistic next steps are:

### Mechanical

- Increase arm speed while preserving repeatability and positional accuracy.
- Design a better enclosure/box for cleaner integration of electronics and mechanics.
- Improve stepper-driver heat management to reduce overheating risks during longer runs.
- Machine critical joint components, especially the axle section linking the forearm to the joint pulley, to improve rigidity and reduce play.
- Reduce backlash and improve overall structural stiffness in the SCARA linkage.

### Vision and Software

- Add automated retraining workflows for the continuously growing dataset.
- Strengthen end-to-end robustness across different lighting conditions and camera positions.

### System Integration

- Add clearer player feedback when invalid or ambiguous board states are detected.
- Extend the UI to expose more debugging and calibration information.
- Improve synchronization between board verification, move planning, and robot execution.

## License

Hardware designs are licensed under
[Creative Commons Attribution 4.0](LICENSE-CC-BY-4.0).

Unless otherwise noted, the code in this repository is licensed under the
[MIT License](LICENSE).
