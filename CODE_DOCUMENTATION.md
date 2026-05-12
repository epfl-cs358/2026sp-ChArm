# ChArm — Code Documentation

This document describes both halves of the ChArm chess-playing SCARA robot:

- the **Arduino firmware** in `arduino_code/` (C++) — drives the steppers, gripper, limit switches, encoder/LCD UI
- the **Python host program** in `python_code/` (Python 3) — does computer vision on the chessboard, runs Stockfish, and tells the Arduino where to go

The two halves are physically connected by **two USB serial links**:

| Link | Arduino end | Python end | Used for |
|------|-------------|------------|----------|
| Manual move serial (`Serial`, 9600 baud) | `main.cpp` command parser | `arduino_bridge.py` (`manual_serial`) | Cartesian moves: `moveXY`, `moveXYZ`, `moveZ`, `OG`/`CG`, `calibrate` |
| UI controller serial (`Serial1`, 115200 baud) | `UIController` | `ArduinoUIControllerLink` | High-level UI events: board check, player-done, difficulty, mode |

The host generally does not speak G-code — it sends short ASCII commands (one per line) that the Arduino parses in `handleCommand()`.

---

## 1. Arduino firmware (`arduino_code/src/`)

### Top-level files

#### `main.cpp`
The entry point compiled to the board. It instantiates every hardware object as a global (steppers, joints, lead screw, arm, gripper, limit switches, UI). Responsibilities:

- `setup()`: configures pins, starts each subsystem, prints the command help.
- `loop()`: reads bytes from `Serial`, builds a line in `cmdBuffer`, and dispatches to `handleCommand()`. In **controller mode** (toggled by `cm`) jog keys (`w/a/s/d`/`u/j`/`v/c`) dispatch immediately without `Enter` so that holding the key produces continuous motion.
- `handleCommand(String cmd)`: the ASCII command parser. Recognised commands:
  - **Single-character (debug stepping)**: `f`/`b` step X, `w`/`s` step Y, `u`/`d` step Z, `c`/`v` close/open gripper.
  - **Single-character (controller mode)**: `w/a/s/d` ±XY by `JOG_XY_MM` (3 mm), `u/j` ±Z by `JOG_Z_MM` (1.5 mm), `c`/`v` gripper.
  - **Multi-character**:
    - `OG` / `CG` — open / close gripper
    - `GS` — gripper status
    - `GA <angle>` — drive gripper servo to a raw angle
    - `angleX <deg>` — move joint 1 absolute
    - `angleY <deg>` — move joint 2 absolute
    - `moveXY <x> <y>` — Cartesian move of the arm
    - `moveZ <mm>` — absolute Z (lead screw)
    - `moveXYZ <x> <y> <z>` — combined move
    - `calibrate` — run the homing routine
    - `controllerMode` / `cm` — toggle keyboard jog
    - `pos` — print current state
- `calibrate()`: Z homes against the bottom switch, lifts 30 mm, then J1 homes against its switch and is repositioned 90° (137° in this build) to call its IK zero. J2 sweeps both ways between switches; the midpoint of the swept range becomes IK zero. Soft limits are written into each `ScaraJoint`.

#### `main2.cpp`
A minimal scope file used only to debug the Z-bottom limit switch — it just prints `digitalRead(Z_LIMIT_BOTTOM_PIN)` in a loop. Not part of the main firmware, kept as an alternate PlatformIO env.

#### `pins.h`
All pin numbers in one place — STEP/DIR for X/Y/Z, the shared `ENABLE_PIN`, three limit switches, the gripper servo pin, the rotary-encoder/button pins (`CLK`, `DT`, `SW`) and the LCD pins.

#### `config.h`
All numeric constants: motor `STEPS_PER_REV`, `MICROSTEPS`, gear ratios for J1/J2, link lengths, lead-screw geometry (`PITCH * STARTS = LEAD`, hence `STEPS_PER_MM`), gripper open/closed angles, default step delay.

---

### Hardware abstractions (`hardware/src/`)

#### `class StepperXYZ`
A thin wrapper around a CNC-shield STEP/DIR driver. The shared `ENABLE` pin is handled in `setup()`.

```cpp
StepperXYZ(uint8_t stepPin, uint8_t dirPin);
void begin();
void step();                    // one pulse in current direction
void step(long steps);          // |steps| pulses; sign chooses direction
void setDirection(bool forward);
bool direction() const;
void setStepDelay(unsigned int microseconds);   // half-period of STEP pulse
unsigned int stepDelay() const;
```

#### `class ScaraJoint`
Angle-aware wrapper around a `StepperXYZ`. Converts degrees ↔ steps using `stepsPerRev * microstep / (gearRatio * 360)`. Carries a `stepResidual` so repeated fractional moves don't accumulate rounding drift. Soft-limit checked.

```cpp
ScaraJoint(StepperXYZ& stepper, float stepsPerRev, int microstep, float gearRatio);
void  moveTo(float angleDeg);
void  moveBy(float deltaDeg);
float angle() const;
void  setZero();                // current pose becomes 0°
void  setAngle(float deg);
void  setMinAngle(float deg);
void  setMaxAngle(float deg);
float stepsPerDegree() const;
```

#### `class LeadScrew`
Same idea as `ScaraJoint` but in millimetres along Z. Soft-clamped to `[0, maxTravel_mm]`.

```cpp
LeadScrew(StepperXYZ& stepper, float stepsPerMM, float maxTravel_mm,
          float gripperLength = 0.0f);
void  moveTo_mm(float mm);
void  moveBy_mm(float mm);
float position_mm() const;
void  setZero();
```

#### `struct IKResult` / `struct FKResult` / `class ScaraKinematics`
Pure-math layer for the planar two-link arm. `inverseKinematics(x, y)` returns `theta1`, `theta2` in degrees plus a `reachable` flag (false when the target is outside the workspace, `|d| > 1`). `forwardKinematics(theta1, theta2)` returns `(x, y)` in mm.

```cpp
struct IKResult { float theta1, theta2; bool reachable; };
struct FKResult { float x, y; };

ScaraKinematics(float j1 = 0, float j2 = 0);
void     setLinks(float j1, float j2);
IKResult inverseKinematics(float x, float y);
FKResult forwardKinematics(float theta1Deg, float theta2Deg);
```

#### `class ScaraArm`
Combines two `ScaraJoint`s with a `ScaraKinematics` solver to expose Cartesian moves. Note the hardware quirk: joint 2's motor is mounted opposite to the IK convention, so the commanded angle is negated in both `moveXY` and `sync`.

```cpp
ScaraArm(ScaraJoint& joint1, ScaraJoint& joint2,
         float j1Length, float j2Length);
bool  moveXY(float x, float y);   // returns false if unreachable
float theta1() const;
float theta2() const;
float x() const;
float y() const;
void  sync();                     // refresh cached (x,y) from joint angles
```

#### `class Gripper`
Wraps a `Servo` for the gripper. `begin()` attaches and opens. `open()` / `close()` move to the configured angles and `delay(500)` to let the servo settle.

```cpp
Gripper(uint8_t servoPin, int openAngle, int closedAngle);
void  begin();
void  open();
void  close();
bool  isOpen() const;
void  goToAngle(float angle);
```

#### `class LimitSwitch`
INPUT_PULLUP wrapper. `isNotTriggered()` returns true while the switch is *un-pressed*. `activeLow=true` means a triggered switch reads LOW.

```cpp
LimitSwitch(uint8_t pin, bool activeLow);
void begin();
bool isNotTriggered() const;
```

#### `limitAxis.h` (free functions)
Homing primitives. Both call `stepper.step()` in a tight loop and consult the switch.

```cpp
long findLimit(StepperXYZ& s, LimitSwitch& sw, bool direction,
               unsigned long debounceMs);   // step until triggered, debounced
long backOff (StepperXYZ& s, LimitSwitch& sw, bool direction,
               unsigned long backOffDelayMs); // step back until released and stable
```

`findLimit` returns the step count to first contact; `backOff` returns the step count to release. `calibrate()` in `main.cpp` uses the difference between J2's two contacts to compute the joint's full mechanical range.

#### UI subsystem

The UI subsystem is currently **wired up but disabled** — `main.cpp` constructs all of the objects but the calls to `uiController.begin()` and `uiController.loop()` are commented out. It is meant to be re-enabled once the host (Python) side of the protocol is in production.

##### `enum InputEvent` / `class ButtonInput`
Polled rotary-encoder + push button. `readEvent()` is non-blocking and returns one of `INPUT_NONE`, `INPUT_NEXT` (CW), `INPUT_PREV` (CCW) or `INPUT_SELECT` (debounced press release).

```cpp
ButtonInput(int clkPin, int dtPin, int swPin);
void       begin();
InputEvent readEvent();
```

##### `class LCDDisplay`
Wrapper around the stock `LiquidCrystal` library. `update(line1, line2)` only redraws lines that actually changed (avoids flicker), and pads/truncates to 16 columns.

```cpp
LCDDisplay(int rs, int e, int d4, int d5, int d6, int d7);
void begin();
void update(String line1, String line2);
void clear();
```

##### Enums and `class UIState`
All UI screens and selections in one place. The enums:
- `UIMode` — `BOOT`, `MENU`, `DIFFICULTY`, `MANUAL_CONTROL`, `MANUAL_ACTIVE`, `CALIBRATION`, `GAME`, `ERROR`
- `MenuItem` — `START_GAME`, `DIFFICULTY_ITEM`, `CALIBRATION_ITEM`, `MANUAL_CONTROL_ITEM`
- `Difficulty` — `EASY`, `MEDIUM`, `HARD`
- `ControlTarget` — `JOINT1`, `JOINT2`, `LEADSCREW`, `GRIPPER`, `BACK_TO_MENU`
- `GripperAction` — `GRIPPER_OPEN`, `GRIPPER_CLOSE`
- `PlayerTurn` — `WHITE`, `BLACK`
- `GameStatus` — `WAITING_PLAYER`, `THINKING`, `MOVING`

`UIState` exposes navigation helpers (`menuNext/Prev`, `controlNext/Prev`, `difficultyNext/Prev`, ...), commit/cancel for the difficulty edit, an error-mode stack (`setMode(ERROR)` remembers the previous mode so `clearError()` can return), and `getLine1()`/`getLine2()` which produce the two LCD strings derived from the current state.

##### `class UIController`
Glues `ButtonInput`, `UIState`, `LCDDisplay`, and the host serial port (`Stream& serial`, defaulting to `Serial1`). Called from the Arduino `loop()`.

```cpp
UIController(ButtonInput&, UIState&, LCDDisplay&, Stream& serial = Serial);
void begin(unsigned long baud = 115200);
void loop();
void sendState();
void sendMessage(const String& msg);
```

Internal flow inside `loop()`:
1. **Mode-entry hook** — when the user enters `CALIBRATION`, immediately emit `CALIBRATE_START`, run the global `calibrate()`, then emit `CALIBRATE_DONE` and bounce back to `MENU`.
2. **Inbound serial** — accumulate one line at a time and route it through `processLine()`.
3. **One button event per pass** — interpret the event in the context of the current `UIMode`. The only outbound messages from button events are: `CHECK_BOARD` (when `START_GAME` is selected), `SET_DIFFICULTY n` (after difficulty commit), `PLAYER_DONE` (when the player presses OK during their turn).
4. **Board-check timeout** — if the host doesn't reply to `CHECK_BOARD` within `boardTimeoutMs` (3 s), enter `ERROR` and emit `BOARD_TIMEOUT`.
5. **LCD refresh** — push the latest two lines from `UIState`.

`processLine()` accepts these commands from the host:
- `GET_STATE` → reply with the serialized state line
- `SET_MODE <n>` → force the UI into a particular `UIMode`
- `BOARD_OK` / `BOARD_FAIL` → resolve a pending `CHECK_BOARD`
- `ERROR_CLEAR` → clear error mode
- `BOT_THINKING` / `BOT_MOVING` → set `GameStatus`
- `PLAYER_TURN_WHITE` / `PLAYER_TURN_BLACK` → set whose turn it is
- anything else → `UNKNOWN_CMD`

`serializeState()` formats one line of the form
`STATE m:<n> menu:<n> diff:<n> control:<n> grip:<n> turn:<n> status:<n> | <line1> | <line2>`.

---

## 2. Python host (`python_code/`)

The package layout is flat under `src/charm/`:

```
charm/
├── arduino/        ← serial bridges
├── chess_engine/   ← Stockfish wrapper
├── game/           ← orchestration + state tracking
├── utils/          ← bitmap helpers
└── vision/         ← board calibration + occupancy / colour detection
```

`main.py` is the end-to-end demo: it grabs an image (file or ESP32-CAM), applies the two-stage calibrated warp, runs the vision pipeline, optionally infers a move, and saves debug images.

### `charm.arduino`

#### `arduino_bridge.py` — manual move link
Opens `serial.Serial('/dev/cu.usbmodem1401', 9600, timeout=2)` at module load. The matching Arduino side is `Serial` (i.e. `main.cpp`'s ASCII command parser).

```python
def send_command(command: str) -> str:
    """Write `<command>\n`, read one reply line, return it stripped."""

def execute_move(uci_move: str, is_capture: bool,
                 is_castling: bool, is_promotion: bool) -> None:
    """Translate a chess move into a sequence of Cartesian commands."""
```

`execute_move` builds the pick-and-place sequence using `coordinate_map.get_square_position()` and the constants `Z_HOVER`, `Z_DOWN`, `T_X/T_Y/T_Z` (trash/captured-piece bin), `H_X/H_Y/H_Z` (home / parked pose):

- **Capture**: hover over destination → drop down → close gripper → carry to bin → drop → open → hover over source → down → close → carry to destination → drop → open → home.
- **Castling**: move the king first, then the rook to its post-castle square, then home. The rook source/target is hardcoded for the four legal castling moves (`e1g1`, `e1c1`, `e8g8`, `e8c8`).
- **Quiet / normal move**: hover over source → down → close → hover over destination → down → open → home.

Every step is one `send_command()` call. Promotion is parsed but not yet specially handled.

#### `coordinate_map.py`
Translates a chess square (e.g. `"e4"`) to physical (x, y) on the board.

```python
def get_square_position(move: str) -> tuple[float, float]:
    col = ord(move[0]) - ord('a')
    row = int(move[1]) - 1
    return (A1_X + col * STEP, A1_Y + row * STEP)
```

`STEP` is currently `37.5` mm. `A1_X`, `A1_Y`, `Z_HOVER`, `Z_DOWN`, `H_X/H_Y/H_Z`, `T_X/T_Y/T_Z` are placeholders (`TODO`) — they must be filled in once the board is mounted and the home/trash positions are calibrated.

#### `uiController_bridge.py` — UI link
Opens its own `serial.Serial(port, baud=115200)` and runs a background reader thread. Matches the Arduino's `Serial1` / `UIController` protocol.

```python
class ArduinoUIControllerLink:
    def __init__(self, port, baud=115200, timeout=1.0,
                 on_check_board=None, on_player_done=None,
                 on_set_difficulty=None, on_line=None): ...
    def set_handlers(self, ...): ...
    def start(self): ...                   # spawn reader thread
    def close(self): ...                   # stop thread + close port

    # Outbound helpers — these are what `GameController` calls
    def send(self, command: str): ...
    def board_ok(self): ...                # → "BOARD_OK"
    def board_fail(self): ...              # → "BOARD_FAIL"
    def bot_thinking(self): ...            # → "BOT_THINKING"
    def bot_moving(self): ...              # → "BOT_MOVING"
    def move_done(self): ...               # → "MOVE_DONE"
    def player_turn_white(self): ...
    def player_turn_black(self): ...
    def set_mode(self, mode: int): ...     # → "SET_MODE <n>"
    def set_difficulty(self, n: int): ...  # → "SET_DIFFICULTY <n>"
    def get_state(self): ...               # → "GET_STATE"
```

The reader thread (`_reader_loop` → `_handle_line`) recognises three Arduino-originated messages and invokes the registered callbacks:

| Arduino sends | Callback invoked | Auto-reply |
|---|---|---|
| `CHECK_BOARD` | `on_check_board() -> bool` | `BOARD_OK` if True, else `BOARD_FAIL` |
| `PLAYER_DONE` | `on_player_done()` | none |
| `SET_DIFFICULTY <n>` | `on_set_difficulty(n)` | `OK` |

Anything else still fires `on_line(line)` if a generic handler was supplied.

### `charm.chess_engine`

#### `best_move.py`
Single function that wraps `python-chess`'s UCI engine adapter.

```python
def get_best_move(board: chess.Board,
                  engine_path: str = "stockfish",
                  think_time: float = 0.1,
                  skill_level: int = 20) -> Optional[chess.Move]:
    """Spawn Stockfish, configure 'Skill Level' (clamped 0..20),
    play one move with a time limit, then quit."""
```

### `charm.game`

This is the brain — it owns the board state, the vision-driven update loop, and the interaction with the Arduino UI link.

#### `state_tracker.py`

```python
Bitmap = list[list[int]]             # 8x8, row 0 = rank 8, col 0 = file a
TrackerStatus = Literal["accepted_legal_move",
                        "unchanged_position",
                        "invalid_observation",
                        "ambiguous_observation"]

@dataclass
class MoveInferenceResult:
    move: Optional[chess.Move]
    mismatch_count: int
    status: TrackerStatus
    matching_move_count: int = 0
```

Free functions:

- `empty_bitmap()` — fresh 8×8 zero matrix.
- `board_to_bitmaps(board)` — convert a `chess.Board` into `(white_bitmap, black_bitmap)`.
- `count_bitmap_mismatches(left, right)` — number of squares where the two 8×8 maps differ.
- `compare_board_to_bitmaps(board, white_obs, black_obs)` — total mismatch between a candidate board and an observation.
- `infer_move_from_bitmaps(board, white_obs, black_obs)` — for each `legal_move`, push it on a copy of the board and pick the candidate that minimises mismatch. Returns `MoveInferenceResult`.

```python
class BoardStateTracker:
    def __init__(self, board: Optional[chess.Board] = None) -> None: ...
    def current_bitmaps(self) -> tuple[Bitmap, Bitmap]: ...
    def infer_move(self, white_obs, black_obs) -> MoveInferenceResult: ...
    def update_from_bitmaps(self, white_obs, black_obs,
                            max_mismatches: int = 0) -> MoveInferenceResult: ...
```

`update_from_bitmaps` is the gatekeeper:
- If the position hasn't changed → status `unchanged_position`.
- If no candidate move brings mismatch ≤ `max_mismatches` → `invalid_observation`.
- If multiple candidates tie → `ambiguous_observation`.
- Otherwise pushes the winning move and returns `accepted_legal_move`.

#### `vision_integration.py`
Bridges vision to the tracker.

```python
@dataclass
class VisionStateUpdateResult:
    pipeline_result: BoardPipelineResult
    inference_result: MoveInferenceResult

def infer_move_from_image(tracker, image_path) -> VisionStateUpdateResult: ...
def update_tracker_from_image(tracker, image_path,
                              max_mismatches=0) -> VisionStateUpdateResult: ...
```

`infer_move_from_image` is read-only (does not mutate the tracker). `update_tracker_from_image` calls `tracker.update_from_bitmaps`, so on success the tracker's internal `chess.Board` advances by one ply.

#### `game_session.py`
A higher-level wrapper that records a transcript of all the calls.

```python
@dataclass
class SessionResult:
    success: bool
    message: str
    move_uci: Optional[str] = None
    motion_step: Optional[str] = None
    mismatch_count: Optional[int] = None

@dataclass
class SessionStep:
    step_index: int
    image_path: str
    success: bool
    message: str
    move_uci: Optional[str] = None
    motion_step: Optional[str] = None
    mismatch_count: Optional[int] = None

class GameSession:
    def __init__(self): ...
    def initialize_from_image(self, image_path,
                              max_mismatches: int = 0) -> SessionResult:
        """Verify the board is in the standard starting position."""
    def process_next_image(self, image_path,
                           max_mismatches: int = 0) -> SessionResult:
        """Run vision + tracker; record the inferred move."""
    def get_move_history(self) -> list[str]: ...
    def print_steps(self) -> None: ...
```

Internally it maintains `self.tracker: BoardStateTracker` and a list of `SessionStep`.

#### `game_controller.py`
The top-level orchestrator. It does **not** decide chess moves itself; it wires events from the Arduino UI to the session, vision and Stockfish.

```python
@dataclass
class GameControllerConfig:
    board_image_provider: Callable[[], str]   # returns image path
    on_player_done: Optional[Callable[[], None]] = None
    on_set_difficulty: Optional[Callable[[int], None]] = None
    engine_path: str = "stockfish"
    think_time: float = 0.1

class GameController:
    DIFFICULTY_MAP = {0: 5, 1: 12, 2: 20}     # Arduino → Stockfish skill

    def __init__(self, ui_link: ArduinoUIControllerLink,
                 session: Optional[GameSession],
                 config: GameControllerConfig): ...
    def start(self): ...                       # opens reader thread
    def stop(self): ...
    def check_board(self) -> bool: ...         # wired to CHECK_BOARD
    def player_done(self) -> None: ...         # wired to PLAYER_DONE
    def set_difficulty(self, difficulty: int) -> None: ...
    def notify_turn_white(self): ...
    def notify_turn_black(self): ...
```

`player_done` is the heart of a turn:
1. Send `BOT_THINKING` to the Arduino.
2. (Optionally) call the app-supplied hook.
3. Ask Stockfish for the best move at the current skill level.
4. Send `BOT_MOVING`, then call `arduino_bridge.execute_move(...)` over the **manual move serial** to physically play the piece.
5. Push the move onto the session's tracker.
6. Send `PLAYER_TURN_WHITE` / `PLAYER_TURN_BLACK` and `MOVE_DONE`.

### `charm.utils.bitmap`

```python
def build_white_black_bitmaps(
    color_results: list[PieceColorResult],
) -> tuple[list[list[int]], list[list[int]]]:
```

Pivots the per-cell colour classifications from vision into the two 8×8 bitmaps the tracker expects.

### `charm.vision`

Vision is split into discrete stages so each one can be tested or visualised in isolation. The expected pipeline at runtime is:

1. **Capture** — `transferphoto.fetch_raw_image()` pulls a JPEG from the ESP32-CAM (`http://.../capture`), decodes it, and writes `latest_raw.jpg`.
2. **First warp** — `four_point_calibration.warp_from_calibration(image, FourPointCalibration, output_size)` projects the four hand-picked outer corners to a square 800×800 image.
3. **Inner refinement** — `four_point_calibration.refine_board_with_inner_corners(...)` does a second perspective transform using the inner-corner calibration so the chessboard fills the frame exactly.
4. **Pipeline** — `pipeline.run_board_pipeline(image_path)` resizes to 800×800, splits to 8×8 cells, runs occupancy + piece-colour detection, builds the bitmaps.

#### `transferphoto.py`
```python
ESP32_URL = "http://172.21.73.228/capture"
RAW_PATH  = "latest_raw.jpg"
def fetch_raw_image() -> str:
    """Download from ESP32-CAM, save to RAW_PATH, return the path."""
```

#### `calibration_config.py`
Just two `Path` constants pointing at the JSON files used for the two warp stages:
- `DEFAULT_BOARD_CALIBRATION_JSON` → `python_code/board_calibration.json`
- `DEFAULT_INNER_WARP_CALIBRATION_JSON` → `python_code/inner_warp_calibration.json`

#### `four_point_calibration.py`
Pure data + transform helpers, no UI.

```python
@dataclass
class FourPointCalibration:
    top_left: tuple[int, int]
    top_right: tuple[int, int]
    bottom_right: tuple[int, int]
    bottom_left: tuple[int, int]
    def as_array(self) -> np.ndarray: ...   # float32, 4x2

@dataclass
class InnerWarpCalibration:                 # same shape, separate name for clarity
    top_left, top_right, bottom_right, bottom_left
    def as_array(self) -> np.ndarray: ...
```

Helpers:
- `draw_calibration_points(image, calibration)` / `draw_inner_warp_points(...)` — annotate the image with the four points and the polygon edges.
- `warp_from_calibration(image, calibration, output_size=800)` — `cv2.getPerspectiveTransform` + `cv2.warpPerspective` to a square.
- `refine_board_with_inner_corners(warped_board, calibration, output_size=800)` — same shape but applied to the already-warped image.
- `crop_and_refit_board(warped_board, left, top, right, bottom, output_size)` — manual margin crop + resize.
- `save_/load_four_point_calibration(...)` and `save_/load_inner_warp_calibration(...)` — JSON IO.

#### `calibrate_board_corners.py` and `calibrate_inner_warp_corners.py`
Two small interactive scripts. Each opens an OpenCV window, lets the user click four points (TL → TR → BR → BL), and writes the resulting JSON. The "inner" script first applies the outer warp so you click on the already-rectified image. Run them once at setup; their output is consumed by `main.py` and `pipeline.py`.

#### `board_detector.py`
An older auto-detection path, currently unused by `pipeline.py` (which assumes pre-calibrated input). Worth knowing in case auto-detection is brought back.

```python
def build_black_mask(image): ...                # HSV mask of the dark border
def build_color_mask(image): ...                # green + pink squares
def contour_to_quad(contour): ...               # 4-point approx via approxPolyDP/minAreaRect
def quad_bounds(corners, image_shape): ...
def candidate_has_board_colors(image, corners,
                               min_color_ratio=0.12) -> bool: ...
def find_largest_quadrilateral(image): ...      # main detector
def draw_detected_corners(image, corners): ...
def draw_black_mask_debug(image): ...
def draw_color_mask_debug(image): ...
```

#### `perspective.py`
Companion utilities (also currently unused by the live pipeline).

```python
def order_points(points: np.ndarray) -> np.ndarray:
    """Sort 4 points to (TL, TR, BR, BL)."""
def crop_inner_board(warped_image, border_ratio=0.035, output_size=800): ...
def warp_board(image, corners, size=800,
               crop_border=True, border_ratio=0.035): ...
```

#### `grid_splitter.py`
Splits the 800×800 warped board into 64 equal cells.

```python
@dataclass
class SquareCell:
    row: int; col: int
    x1: int; y1: int; x2: int; y2: int
    image: np.ndarray

def extract_8x8_cells(board_image) -> list[SquareCell]: ...
def draw_8x8_grid(board_image) -> np.ndarray:           # blue grid overlay
```

#### `occupancy_detector.py`
Per-cell edge-density check on the central 60% ROI: Canny, mean, threshold.

```python
@dataclass
class OccupancyResult:
    row: int; col: int; occupied: bool; score: float

def compute_occupancy_score(cell_image) -> float: ...
def detect_occupancy(cells, threshold: float = 8) -> list[OccupancyResult]: ...
def occupancy_to_matrix(results) -> list[list[int]]: ...
def draw_occupancy_debug(board_image, cells, results) -> np.ndarray: ...
```

(`pipeline.run_board_pipeline` overrides the default and uses `threshold=2.5`.)

#### `piece_color_detector.py`
For occupied cells only, classify the piece colour from a brightness score on the central 50% ROI. Two thresholds (white_threshold, black_threshold) carve out an "unknown" middle band.

```python
PieceColorLabel = Literal["white", "black", "unknown"]

@dataclass
class PieceColorResult:
    row: int; col: int
    occupied: bool
    color: PieceColorLabel
    brightness_score: float

def compute_piece_brightness_score(cell_image) -> float: ...
def detect_piece_colors(cells, occupancy_results,
                        white_threshold: float = 125.0,
                        black_threshold: float = 110.0) -> list[PieceColorResult]: ...
def draw_piece_color_debug(board_image, cells, color_results) -> np.ndarray: ...
```

#### `pipeline.py`
The post-calibration pipeline. Consumes a path, returns one fat dataclass with every intermediate image plus the final bitmaps.

```python
@dataclass
class BoardPipelineResult:
    original_image, roi_debug_image, cropped_board_image,
    preprocessing_debug_image, black_mask_debug_image,
    color_mask_debug_image, corners_debug_image,
    warped_board, grid_debug_image, occupancy_debug_image,
    piece_color_debug_image: np.ndarray
    occupancy_matrix, white_bitmap, black_bitmap: list[list[int]]

def run_board_pipeline(image_path: str) -> BoardPipelineResult: ...
```

The result struct still carries fields from the older auto-detection path (`black_mask_debug_image` etc.) for backwards compatibility — they are set to copies of the input image now.

---

## 3. How the two halves talk

There are two completely separate serial conversations.

### 3.1 Manual move serial (`Serial`, 9600 baud)
Used by `arduino_bridge.execute_move()` on the host and `main.cpp` on the Arduino.

```
   Python                                           Arduino (main.cpp)
   ──────                                           ──────────────────
   send_command("moveXYZ 120 80 30\n")  ─────►    handleCommand("moveXYZ 120 80 30")
                                                    arm.moveXY(120, 80)
                                                    leadScrew.moveTo_mm(30)
                                                    Serial.println("Position: (...)");
   manual_serial.readline()             ◄─────    serial reply
```

Every command is one line of ASCII. The Arduino prints a one-line reply (often the new position) and `send_command()` returns it. There is no acknowledgement protocol beyond "I read a line back" — moves are blocking on the Arduino because each `step()` is `delayMicroseconds`-based.

Vocabulary used today by `execute_move`:
- `moveXYZ <x> <y> <z>` — fly to a Cartesian point.
- `moveZ <mm>` — Z only.
- `OG` / `CG` — open / close the gripper.
- (`calibrate` is also available but invoked manually, not from `execute_move`.)

### 3.2 UI controller serial (`Serial1`, 115200 baud)
Used by `ArduinoUIControllerLink` on the host and `UIController` on the Arduino. The Arduino is the source of truth for the **user-facing** state — buttons rotate menus and the Arduino tells the host when something interesting happens. The host replies with high-level outcomes.

#### Arduino → Host
| Message | When | Host action |
|---|---|---|
| `CALIBRATE_START` / `CALIBRATE_DONE` | bracketing the homing routine | informational |
| `CHECK_BOARD` | user picked "Start Game" | invoke `on_check_board()` and reply `BOARD_OK` or `BOARD_FAIL` (within 3 s) |
| `BOARD_OK_ACK` / `BOARD_FAIL_ACK` | echo after host reply | informational |
| `BOARD_TIMEOUT` | host didn't reply in time | UI is now in `ERROR` |
| `SET_DIFFICULTY <n>` | user committed a new difficulty | invoke `on_set_difficulty(n)`; reply `OK` |
| `PLAYER_DONE` | user pressed OK during their turn | invoke `on_player_done()` |
| `STATE m:.. menu:.. … | <l1> | <l2>` | reply to host's `GET_STATE` | informational |
| `UNKNOWN_CMD` | host sent something the firmware didn't recognise | log |

#### Host → Arduino
| Message | When | Arduino action |
|---|---|---|
| `BOARD_OK` / `BOARD_FAIL` | reply to `CHECK_BOARD` | move to `GAME` (waiting for player) or `ERROR` |
| `ERROR_CLEAR` | dismiss an error remotely | restore previous mode |
| `BOT_THINKING` / `BOT_MOVING` | during host turn | update `GameStatus` shown on LCD |
| `PLAYER_TURN_WHITE` / `PLAYER_TURN_BLACK` | after a robot move | switch turn indicator |
| `SET_MODE <n>` | force a UI mode | `uiState.setMode(...)` |
| `SET_DIFFICULTY <n>` | mirror UI difficulty | (currently a no-op handler) |
| `GET_STATE` | poll the UI | reply with the `STATE …` line |

### 3.3 Typical end-to-end turn

A normal "human plays, then robot replies" cycle wires both serials together:

```
 USER turns encoder, presses SELECT on START_GAME
   └─ Arduino UIController:    CHECK_BOARD ──► host
                                              │
                                              ▼  GameController.check_board()
                                              ▼  GameSession.initialize_from_image()
                                              ▼  → BOARD_OK
   ─◄ host:                             BOARD_OK
   Arduino enters GAME, WAITING_PLAYER

 USER moves a piece, presses SELECT
   └─ Arduino UIController:    PLAYER_DONE ──► host
                                              │
                                              ▼  GameController.player_done()
                                              ▼  → BOT_THINKING (UI serial)
                                              ▼  Stockfish.get_best_move()
                                              ▼  → BOT_MOVING (UI serial)
                                              ▼  arduino_bridge.execute_move()
                                              ▼     send_command("moveXYZ ...")  ──► (Serial)
                                              ▼     send_command("CG"/"OG")      ──► (Serial)
                                              ▼     ...
                                              ▼  → PLAYER_TURN_WHITE/BLACK + MOVE_DONE (UI serial)
   Arduino UI: WAITING_PLAYER again
```

The two serial channels are deliberately separate so the move-execution stream can stay simple ("send line, get reply") without having to multiplex with UI events.

---

## 4. Building / running

### Arduino
PlatformIO project in `arduino_code/`. Two envs are visible: the main `megaatmega2560` build (which links `main.cpp`) and a `debug_limit` env that links `main2.cpp`. Choose one in `platformio.ini` and `pio run -t upload`.

### Python
```
cd python_code
pip install -r requirements.txt

# one-time, with the camera looking at the empty board:
python src/charm/vision/calibrate_board_corners.py
python src/charm/vision/calibrate_inner_warp_corners.py

# then run the demo (file or live camera):
python main.py --image ../latest_raw.jpg
python main.py --camera
```

Before any real move can be sent through `arduino_bridge`, the `TODO`s in `coordinate_map.py` (`A1_X`, `A1_Y`, `Z_HOVER`, `Z_DOWN`, home, trash) must be filled in with measured millimetre values for the actual rig.
