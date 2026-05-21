"""CV router with primary/fallback retry.

Two chess-vision pipelines coexist in this codebase:

  - ``"vision"``  → classical CV (``charm.vision.pipeline.run_board_pipeline``)
  - ``"cnn"``     → CNN classifier (``charm.vision.cnn_classifier.CnnBoardClassifier``)

The router does not know about chess rules. It owns three things only:

  1. The order to try the pipelines in (primary first, then the other).
  2. How many fresh-capture attempts each pipeline gets.
  3. When to stop (the caller decides whether an attempt validated).

The caller passes a ``capture_fn`` per mode (each call must grab a fresh frame
and run that mode's pipeline) and an ``on_each_attempt`` callback that is the
sole judge of success — typically by feeding the bitmaps into
``GameSession.process_bitmaps`` / ``initialize_from_bitmaps``.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, Optional


ModeName = Literal["vision", "cnn"]

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[3] / "cv_router_config.json"

logger = logging.getLogger(__name__)


@dataclass
class RouterConfig:
    primary: ModeName = "vision"
    attempts_each: int = 5
    auto_save_validated: bool = True
    dataset_name: str = "validated_live"

    @staticmethod
    def load(path: Path = DEFAULT_CONFIG_PATH) -> "RouterConfig":
        if not path.exists():
            return RouterConfig()
        try:
            data = json.loads(path.read_text())
        except Exception as exc:
            logger.warning("Could not parse %s: %s — using defaults", path, exc)
            return RouterConfig()
        return RouterConfig(
            primary=data.get("primary", "vision"),
            attempts_each=int(data.get("attempts_each", 5)),
            auto_save_validated=bool(data.get("auto_save_validated", True)),
            dataset_name=str(data.get("dataset_name", "validated_live")),
        )

    def save(self, path: Path = DEFAULT_CONFIG_PATH) -> None:
        path.write_text(
            json.dumps(
                {
                    "primary": self.primary,
                    "attempts_each": self.attempts_each,
                    "auto_save_validated": self.auto_save_validated,
                    "dataset_name": self.dataset_name,
                },
                indent=2,
            )
        )


@dataclass
class CaptureOutcome:
    """One pipeline run on one fresh frame.

    ``payload`` is the pipeline-specific debug bundle (e.g., the dict that
    ``_run_cnn_game_scan`` already returns). The router forwards it untouched.
    ``refined_image`` is the 800×800 BGR ndarray, kept so
    ``validated_capture.save_validated_capture`` has something to slice.
    """

    white_bitmap: list[list[int]]
    black_bitmap: list[list[int]]
    payload: dict[str, Any]
    refined_image: Any = None  # numpy.ndarray, kept loose to avoid hard cv2 import


@dataclass
class AttemptDecision:
    """Returned by the caller's ``on_each_attempt`` callback.

    ``success=True`` short-circuits the retry loop; the matching capture is
    treated as the winning observation.
    """

    success: bool
    error: Optional[str] = None
    info: Optional[dict[str, Any]] = None


@dataclass
class AttemptRecord:
    mode: ModeName
    index: int
    success: bool
    error: Optional[str] = None
    elapsed_ms: float = 0.0


@dataclass
class RouterResult:
    success: bool
    mode_used: Optional[ModeName]
    capture: Optional[CaptureOutcome]
    attempts: list[AttemptRecord] = field(default_factory=list)
    final_error: Optional[str] = None

    def attempts_by_mode(self) -> dict[ModeName, int]:
        out: dict[ModeName, int] = {"vision": 0, "cnn": 0}
        for a in self.attempts:
            out[a.mode] += 1
        return out


def _other_mode(mode: ModeName) -> ModeName:
    return "cnn" if mode == "vision" else "vision"


class CVRouter:
    """Primary/fallback retry driver for the two chess-vision pipelines."""

    def __init__(self, config: Optional[RouterConfig] = None):
        self.config = config or RouterConfig.load()

    def scan(
        self,
        capture_fn_by_mode: dict[ModeName, Callable[[], CaptureOutcome]],
        on_each_attempt: Callable[[ModeName, int, CaptureOutcome], AttemptDecision],
    ) -> RouterResult:
        """Run primary then fallback, ``attempts_each`` tries each, stop on success."""
        order: tuple[ModeName, ModeName] = (self.config.primary, _other_mode(self.config.primary))
        attempts: list[AttemptRecord] = []
        last_error: Optional[str] = None

        for mode in order:
            capture_fn = capture_fn_by_mode.get(mode)
            if capture_fn is None:
                # Caller decided this mode is unavailable (e.g. no CNN model
                # loaded). Skip silently — recording a phantom attempt would
                # just confuse the UI.
                continue

            for i in range(self.config.attempts_each):
                t0 = time.perf_counter()
                try:
                    capture = capture_fn()
                except Exception as exc:
                    elapsed = (time.perf_counter() - t0) * 1000.0
                    logger.warning("%s capture attempt %d failed: %s", mode, i, exc)
                    attempts.append(
                        AttemptRecord(
                            mode=mode,
                            index=i,
                            success=False,
                            error=f"capture: {exc}",
                            elapsed_ms=elapsed,
                        )
                    )
                    last_error = f"{mode}: {exc}"
                    continue

                try:
                    decision = on_each_attempt(mode, i, capture)
                except Exception as exc:
                    elapsed = (time.perf_counter() - t0) * 1000.0
                    logger.exception("%s validator attempt %d crashed", mode, i)
                    attempts.append(
                        AttemptRecord(
                            mode=mode,
                            index=i,
                            success=False,
                            error=f"validator: {exc}",
                            elapsed_ms=elapsed,
                        )
                    )
                    last_error = f"{mode}: validator crashed"
                    continue

                elapsed = (time.perf_counter() - t0) * 1000.0
                attempts.append(
                    AttemptRecord(
                        mode=mode,
                        index=i,
                        success=decision.success,
                        error=decision.error,
                        elapsed_ms=elapsed,
                    )
                )
                if decision.success:
                    return RouterResult(
                        success=True,
                        mode_used=mode,
                        capture=capture,
                        attempts=attempts,
                    )
                else:
                    last_error = decision.error or last_error

        return RouterResult(
            success=False,
            mode_used=None,
            capture=None,
            attempts=attempts,
            final_error=last_error or "no attempt validated",
        )
