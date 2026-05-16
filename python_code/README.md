# ChArm — Python side

Python code for the ChArm chess-playing SCARA robot. Handles computer vision,
chess logic (python-chess + stockfish), and serial communication with the
Arduino that drives the arm.

## Install

```
pip install -r requirements.txt
```

## Run

```
python main.py
```

## Project layout

```
python_code/
├── main.py                 
├── requirements.txt
├── src/charm/
│   ├── vision/
│   ├── chess_engine/
│   ├── arduino/
│   ├── game/
│   └── utils/
└── tests/
```

## What each module is expected to contain

Each module should expose one main class so other contributors can build on
top of it without touching unrelated parts. The names and signatures below
are suppositions — adjust as the design settles.

### `src/charm/vision/`
Chessboard recognition from a camera feed.
- Responsibilities:
  - grab a frame from the camera,
  - detect the board and the per-square occupancy,
  - output an 8x8 occupancy bitmap consumed by

### `src/charm/chess_engine/`
Everything that reasons about the game itself (python-chess + stockfish).

### `src/charm/arduino/`
Serial bridge to the Arduino (pyserial).

### `src/charm/game/`
Top-level orchestration.

### `src/charm/utils/`
Shared helpers used by more than one module. Most likely home of the bitmap
format definition and any small conversion helpers

### `tests/`
Unit tests, one subfolder or file per module above.

## Dependencies

See `requirements.txt`.