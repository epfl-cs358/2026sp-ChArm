from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
SRC_PATH = ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from charm.game import GameSession


def print_result(title: str, result) -> None:
    print(title)
    print("success =", result.success)
    print("message =", result.message)
    print("move_uci =", result.move_uci)
    print("motion_step =", result.motion_step)
    print("mismatch_count =", result.mismatch_count)
    print()


def main() -> None:
    session = GameSession()

    initial_image = ROOT / "test_images" / "step0.png"
    after_e2e4_image = ROOT / "test_images" / "step1.png"
    after_e7e5_image = ROOT / "test_images" / "step2.png"
    after_g1f3_image = ROOT / "test_images" / "step3.png"

    init_result = session.initialize_from_image(str(initial_image), max_mismatches=0)
    print_result("Initialization", init_result)

    if not init_result.success:
        return

    step_result = session.process_next_image(str(after_e2e4_image), max_mismatches=0)
    print_result("Next move", step_result)

    step_result2 = session.process_next_image(str(after_e7e5_image), max_mismatches=0)
    print_result("Next move", step_result2)

    step_result3 = session.process_next_image(str(after_g1f3_image), max_mismatches=0)
    print_result("Next move", step_result3)




if __name__ == "__main__":
    main()