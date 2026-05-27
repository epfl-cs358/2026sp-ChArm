from charm.game.state_tracker import (
    BoardStateTracker,
    MoveInferenceResult,
    TrackerStatus,
    board_to_bitmaps,
    infer_move_from_bitmaps,
)
from charm.game.vision_integration import (
    VisionStateUpdateResult,
    infer_move_from_image,
    update_tracker_from_image,
)
from charm.game.game_session import GameSession, SessionResult, SessionStep


def __getattr__(name: str):
    if name in {"GameController", "GameControllerConfig"}:
        from charm.game.game_controller import GameController, GameControllerConfig

        return {
            "GameController": GameController,
            "GameControllerConfig": GameControllerConfig,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "BoardStateTracker",
    "MoveInferenceResult",
    "TrackerStatus",
    "VisionStateUpdateResult",
    "board_to_bitmaps",
    "infer_move_from_bitmaps",
    "infer_move_from_image",
    "update_tracker_from_image",
    "GameSession",
    "GameController",
    "GameControllerConfig",
    "SessionResult",
    "SessionStep",
]
