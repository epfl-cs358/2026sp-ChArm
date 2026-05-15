from __future__ import annotations

from pathlib import Path
import sys
import argparse
import shutil

import chess


# ---------------------------------------------------------------------
# Project path setup
# This file is located at:
#   python_code/tests/test_e2e_vision_to_move.py
#
# Therefore:
#   parents[1] = python_code/
# ---------------------------------------------------------------------
PYTHON_CODE_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PYTHON_CODE_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from charm.game import GameSession
from charm.vision.calibrated_pipeline import run_calibrated_board_pipeline
from charm.vision.transferphoto import fetch_raw_image


# ---------------------------------------------------------------------
# Terminal helpers
# ---------------------------------------------------------------------
def print_section(title: str) -> None:
    print()
    print("=" * 90)
    print(title)
    print("=" * 90)


def prompt_enter(message: str) -> None:
    print()
    print(message)
    input("Press ENTER when ready...")


def ask_yes_no(message: str) -> bool:
    while True:
        answer = input(f"{message} [y/n]: ").strip().lower()

        if answer in {"y", "yes"}:
            return True

        if answer in {"n", "no"}:
            return False

        print("Please type y or n.")


def ask_player_color() -> str:
    while True:
        answer = input("Choose your color [w/b]: ").strip().lower()

        if answer in {"w", "white"}:
            return "white"

        if answer in {"b", "black"}:
            return "black"

        print("Please type w/white or b/black.")


def print_result(title: str, result) -> None:
    print_section(title)
    print("success        =", getattr(result, "success", None))
    print("message        =", getattr(result, "message", None))
    print("move_uci       =", getattr(result, "move_uci", None))
    print("motion_step    =", getattr(result, "motion_step", None))
    print("mismatch_count =", getattr(result, "mismatch_count", None))


# ---------------------------------------------------------------------
# Image providers
# ---------------------------------------------------------------------
class MockImageProvider:
    """
    Local image provider used when ESP32-CAM is not available.

    Images are consumed in order:

      1. initial board image
      2. optional retry/stability images if used
      3. after player move
      4. after robot move verification
      5. after player move
      6. after robot move verification
      ...

    For the first mock test, choose player = white and answer no to optional
    extra checks, so image order is simple:
      step0 = initial board
      step1 = after player move
      step2 = after robot move verification
      step3 = next player move
    """

    def __init__(self, image_paths: list[Path]) -> None:
        if not image_paths:
            raise ValueError("MockImageProvider requires at least one image.")

        self.image_paths = [Path(path) for path in image_paths]
        self.index = 0

        for path in self.image_paths:
            if not path.exists():
                raise FileNotFoundError(f"Mock image not found: {path}")

    def capture(self, output_copy_path: Path) -> Path:
        if self.index >= len(self.image_paths):
            raise RuntimeError(
                "No more mock images available. "
                "Provide more images with --mock-images."
            )

        source = self.image_paths[self.index]
        self.index += 1

        output_copy_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, output_copy_path)

        print(f"[MOCK CAMERA] Using image {self.index}/{len(self.image_paths)}: {source}")
        print(f"[MOCK CAMERA] Copied snapshot to: {output_copy_path}")

        return output_copy_path


def capture_from_esp32(output_copy_path: Path) -> Path:
    """
    Capture one image using transferphoto.fetch_raw_image().

    fetch_raw_image() saves:
      python_code/latest_raw.jpg

    This function immediately copies it into the E2E debug folder so every
    step has its own snapshot.
    """
    output_copy_path.parent.mkdir(parents=True, exist_ok=True)

    latest_raw_path = Path(fetch_raw_image())

    if not latest_raw_path.exists():
        raise FileNotFoundError(
            f"fetch_raw_image() returned missing path: {latest_raw_path}"
        )

    shutil.copy2(latest_raw_path, output_copy_path)

    print(f"[ESP32-CAM] Latest raw image: {latest_raw_path}")
    print(f"[ESP32-CAM] Copied snapshot to: {output_copy_path}")

    return output_copy_path


def capture_image(
    output_copy_path: Path,
    mock_provider: MockImageProvider | None,
) -> Path:
    if mock_provider is not None:
        return mock_provider.capture(output_copy_path)

    return capture_from_esp32(output_copy_path)


# ---------------------------------------------------------------------
# Vision helper
# ---------------------------------------------------------------------
def calibrate_raw_snapshot(
    raw_image_path: Path,
    output_dir: Path,
    name_prefix: str,
    board_calibration_json: Path,
    inner_warp_json: Path,
):
    """
    raw image
    -> calibration method 1
    -> calibration method 2
    -> board pipeline
    """
    result = run_calibrated_board_pipeline(
        raw_image_path=raw_image_path,
        four_point_calibration_path=board_calibration_json,
        inner_warp_calibration_path=inner_warp_json,
        output_dir=output_dir,
        name_prefix=name_prefix,
    )

    print("[VISION] first_warp        =", result.first_warp_path)
    print("[VISION] refined_warp      =", result.refined_warp_path)
    print("[VISION] grid_debug        =", result.grid_debug_path)
    print("[VISION] occupancy_debug   =", result.occupancy_debug_path)
    print("[VISION] piece_color_debug =", result.piece_color_debug_path)

    return result


# ---------------------------------------------------------------------
# Arm helper
# ---------------------------------------------------------------------
def send_robot_move_to_arm(
    session: GameSession,
    move_uci: str,
    real_arm: bool,
) -> bool:
    """
    Send Stockfish move to the arm.

    Default is mock mode.
    Real arm mode imports arduino_bridge only at execution time, so software
    tests do not fail because of missing serial port.
    """
    board = session.get_current_board()

    if board is None:
        print("[ARM] No internal board available.")
        return False

    try:
        move = chess.Move.from_uci(move_uci)
    except ValueError:
        print(f"[ARM] Invalid UCI move: {move_uci}")
        return False

    is_capture = board.is_capture(move)
    is_castling = board.is_castling(move)
    is_promotion = move.promotion is not None

    print_section("Send robot move to arm")
    print("move_uci     =", move_uci)
    print("is_capture   =", is_capture)
    print("is_castling  =", is_castling)
    print("is_promotion =", is_promotion)

    if not real_arm:
        print()
        print("[MOCK ARM] Not sending to Arduino.")
        print("[MOCK ARM] Manually execute or pretend the robot executed this move.")
        input("[MOCK ARM] Press ENTER after the robot move is complete...")
        return True

    try:
        from charm.arduino.arduino_bridge import execute_move
    except Exception as exc:
        print("[ARM] Could not import Arduino bridge.")
        print("Error:", exc)
        return False

    try:
        execute_move(
            move_uci,
            is_capture=is_capture,
            is_castling=is_castling,
            is_promotion=is_promotion,
        )
    except Exception as exc:
        print("[ARM] execute_move failed.")
        print("Error:", exc)
        return False

    return True


# ---------------------------------------------------------------------
# Robot turn
# ---------------------------------------------------------------------
def run_robot_turn(
    session: GameSession,
    output_dir: Path,
    turn_index: int,
    board_calibration_json: Path,
    inner_warp_json: Path,
    max_mismatches: int,
    real_arm: bool,
    engine_path: str,
    think_time: float,
    skill_level: int,
    mock_provider: MockImageProvider | None,
    reason: str,
) -> bool:
    print_section(f"Robot turn — {reason}")

    robot_result = session.compute_robot_move(
        engine_path=engine_path,
        think_time=think_time,
        skill_level=skill_level,
    )

    print_result("Stockfish result", robot_result)

    if not robot_result.success or robot_result.move_uci is None:
        print("[E2E] Could not compute robot move.")
        return False

    expected_robot_move = robot_result.move_uci

    arm_ok = send_robot_move_to_arm(
        session=session,
        move_uci=expected_robot_move,
        real_arm=real_arm,
    )

    if not arm_ok:
        print("[E2E] Arm execution failed.")
        return False

    prompt_enter(
        "Robot move is finished.\n"
        "Now we will capture a verification image."
    )

    raw_after_robot = capture_image(
        output_copy_path=output_dir / f"turn_{turn_index:03d}_after_robot_raw.jpg",
        mock_provider=mock_provider,
    )

    calibrated_after_robot = calibrate_raw_snapshot(
        raw_image_path=raw_after_robot,
        output_dir=output_dir / f"turn_{turn_index:03d}_after_robot",
        name_prefix=f"turn_{turn_index:03d}_after_robot",
        board_calibration_json=board_calibration_json,
        inner_warp_json=inner_warp_json,
    )

    verify_result = session.verify_expected_move_from_image(
        image_path=str(calibrated_after_robot.refined_warp_path),
        expected_move_uci=expected_robot_move,
        max_mismatches=max_mismatches,
    )

    print_result("Robot move verification", verify_result)

    if not verify_result.success:
        print("[E2E] Robot move verification failed.")
        return ask_yes_no("Continue anyway?")

    print("[E2E] Robot move verified.")
    return True


# ---------------------------------------------------------------------
# Main E2E flow
# ---------------------------------------------------------------------
def run_e2e(
    board_calibration_json: Path,
    inner_warp_json: Path,
    output_dir: Path,
    max_mismatches: int,
    real_arm: bool,
    engine_path: str,
    think_time: float,
    skill_level: int,
    mock_provider: MockImageProvider | None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    print_section("E2E Vision-to-Move Test")
    print("PYTHON_CODE_ROOT       =", PYTHON_CODE_ROOT)
    print("SRC_PATH               =", SRC_PATH)
    print("camera_mode            =", "mock-images" if mock_provider else "esp32-cam")
    print("board_calibration_json =", board_calibration_json)
    print("inner_warp_json        =", inner_warp_json)
    print("output_dir             =", output_dir)
    print("max_mismatches         =", max_mismatches)
    print("real_arm               =", real_arm)
    print("engine_path            =", engine_path)
    print("think_time             =", think_time)
    print("skill_level            =", skill_level)

    if not board_calibration_json.exists():
        raise FileNotFoundError(
            f"Board calibration JSON not found: {board_calibration_json}"
        )

    if not inner_warp_json.exists():
        raise FileNotFoundError(
            f"Inner warp calibration JSON not found: {inner_warp_json}"
        )

    session = GameSession()

    # -----------------------------------------------------------------
    # 1. Wait for start
    # -----------------------------------------------------------------
    print_section("Start")
    prompt_enter(
        "Ready to start.\n"
        "Place the chessboard in the standard initial position.\n"
        "When the board is ready, press ENTER."
    )

    # -----------------------------------------------------------------
    # 2. Capture initial board
    # -----------------------------------------------------------------
    print_section("Capture initial board")

    raw_initial = capture_image(
        output_copy_path=output_dir / "initial_raw.jpg",
        mock_provider=mock_provider,
    )

    calibrated_initial = calibrate_raw_snapshot(
        raw_image_path=raw_initial,
        output_dir=output_dir / "initial_calibrated",
        name_prefix="initial",
        board_calibration_json=board_calibration_json,
        inner_warp_json=inner_warp_json,
    )

    # -----------------------------------------------------------------
    # 3. Validate initial board
    # -----------------------------------------------------------------
    print_section("Validate initial board")

    init_result = session.initialize_from_image(
        image_path=str(calibrated_initial.refined_warp_path),
        max_mismatches=max_mismatches,
    )

    print_result("Initial board validation", init_result)

    if not init_result.success:
        print("[E2E] Initial board is invalid.")
        print("Open the debug images and fix calibration / thresholds / board setup.")
        return

    # -----------------------------------------------------------------
    # 4. Ask player color and start game
    # -----------------------------------------------------------------
    print_section("Choose player color")

    player_color = ask_player_color()

    start_result = session.start_game(player_color=player_color)  # type: ignore[arg-type]
    print_result("Start game", start_result)

    if not start_result.success:
        print("[E2E] Could not start game.")
        return

    print("player_color =", session.get_player_color())
    print("robot_color  =", session.get_robot_color())

    turn_index = 1

    # -----------------------------------------------------------------
    # 5. If robot is white, robot moves first
    # -----------------------------------------------------------------
    if session.robot_moves_first():
        ok = run_robot_turn(
            session=session,
            output_dir=output_dir,
            turn_index=turn_index,
            board_calibration_json=board_calibration_json,
            inner_warp_json=inner_warp_json,
            max_mismatches=max_mismatches,
            real_arm=real_arm,
            engine_path=engine_path,
            think_time=think_time,
            skill_level=skill_level,
            mock_provider=mock_provider,
            reason="robot is white, first move",
        )

        if not ok:
            print("[E2E] Robot first move failed.")
            return

        turn_index += 1

    # -----------------------------------------------------------------
    # 6. Main loop
    # -----------------------------------------------------------------
    while True:
        print_section(f"Turn {turn_index} — player move")
        print("Type:")
        print("  n = player has moved, capture and process")
        print("  q = quit")

        command = input("> ").strip().lower()

        if command == "q":
            print("[E2E] Quit requested.")
            break

        if command != "n":
            print("Unknown command. Please type n or q.")
            continue

        prompt_enter(
            "Make your move on the physical board.\n"
            "After moving, remove your hand/tools from the camera view."
        )

        # -------------------------------------------------------------
        # Capture after player move
        # -------------------------------------------------------------
        raw_after_player = capture_image(
            output_copy_path=output_dir / f"turn_{turn_index:03d}_after_player_raw.jpg",
            mock_provider=mock_provider,
        )

        calibrated_after_player = calibrate_raw_snapshot(
            raw_image_path=raw_after_player,
            output_dir=output_dir / f"turn_{turn_index:03d}_after_player",
            name_prefix=f"turn_{turn_index:03d}_after_player",
            board_calibration_json=board_calibration_json,
            inner_warp_json=inner_warp_json,
        )

        # -------------------------------------------------------------
        # Detect player move
        # -------------------------------------------------------------
        player_result = session.process_player_move_from_image(
            image_path=str(calibrated_after_player.refined_warp_path),
            max_mismatches=max_mismatches,
        )

        print_result("Player move detection", player_result)

        if not player_result.success:
            print("[E2E] Player move detection failed.")
            if not ask_yes_no("Continue anyway?"):
                break
            continue

        print("[E2E] Detected player move:", player_result.move_uci)

        # -------------------------------------------------------------
        # Robot computes, moves, and verifies
        # -------------------------------------------------------------
        ok = run_robot_turn(
            session=session,
            output_dir=output_dir,
            turn_index=turn_index,
            board_calibration_json=board_calibration_json,
            inner_warp_json=inner_warp_json,
            max_mismatches=max_mismatches,
            real_arm=real_arm,
            engine_path=engine_path,
            think_time=think_time,
            skill_level=skill_level,
            mock_provider=mock_provider,
            reason="after player move",
        )

        if not ok:
            print("[E2E] Robot turn failed.")
            if not ask_yes_no("Continue to next turn anyway?"):
                break

        print("[E2E] Current move history:", session.get_move_history())
        print("[E2E] Current FEN:", session.get_current_fen())

        turn_index += 1

    # -----------------------------------------------------------------
    # Final summary
    # -----------------------------------------------------------------
    print_section("Final summary")
    print("Move history:", session.get_move_history())
    print("Final FEN:", session.get_current_fen())
    session.print_steps()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Interactive E2E test: start -> capture initial board -> validate -> "
            "choose color -> player move -> Stockfish -> arm/mock -> verification."
        )
    )

    parser.add_argument(
        "--mock-images",
        type=Path,
        nargs="+",
        default=None,
        help=(
            "Use local images instead of ESP32-CAM. "
            "Images are consumed in order: initial, after-player, after-robot, ..."
        ),
    )

    parser.add_argument(
        "--board-calibration-json",
        type=Path,
        default=PYTHON_CODE_ROOT / "board_calibration.json",
        help="Calibration method 1 JSON file.",
    )

    parser.add_argument(
        "--inner-warp-json",
        type=Path,
        default=PYTHON_CODE_ROOT / "inner_warp_calibration.json",
        help="Calibration method 2 JSON file.",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PYTHON_CODE_ROOT / "e2e_debug" / "interactive_e2e",
        help=(
            "Output directory for snapshots and debug images. "
            "Files are overwritten if names match."
        ),
    )

    parser.add_argument(
        "--max-mismatches",
        type=int,
        default=0,
        help="Maximum allowed bitmap mismatches.",
    )

    parser.add_argument(
        "--real-arm",
        action="store_true",
        help="Actually call Arduino execute_move(). Default is mock mode.",
    )

    parser.add_argument(
        "--engine-path",
        type=str,
        default="stockfish",
        help="Path to Stockfish executable.",
    )

    parser.add_argument(
        "--think-time",
        type=float,
        default=0.1,
        help="Stockfish thinking time in seconds.",
    )

    parser.add_argument(
        "--skill-level",
        type=int,
        default=12,
        help="Stockfish skill level from 0 to 20.",
    )

    args = parser.parse_args()

    mock_provider = (
        MockImageProvider(args.mock_images)
        if args.mock_images is not None
        else None
    )

    run_e2e(
        board_calibration_json=args.board_calibration_json,
        inner_warp_json=args.inner_warp_json,
        output_dir=args.output_dir,
        max_mismatches=args.max_mismatches,
        real_arm=args.real_arm,
        engine_path=args.engine_path,
        think_time=args.think_time,
        skill_level=args.skill_level,
        mock_provider=mock_provider,
    )


if __name__ == "__main__":
    main()