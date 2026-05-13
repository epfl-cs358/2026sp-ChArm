from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path


DEFAULT_SQUARE_SIZE_MM = 37.5
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[4] / "robot_calibration.json"
PIECE_TYPES = ("pawn", "knight", "bishop", "rook", "queen", "king")


@dataclass(frozen=True)
class Point2D:
    x: float
    y: float


@dataclass(frozen=True)
class Point3D:
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class BoardCalibration:
    """Maps chess squares to robot coordinates in millimeters.

    `a1` is the center of square a1. `file_vector` is one square step from
    a-file to b-file. `rank_vector` is one square step from rank 1 to rank 2.
    This supports normal, rotated, or mirrored board placement.
    """

    a1: Point2D = field(default_factory=lambda: Point2D(0.0, 0.0))
    file_vector: Point2D = field(default_factory=lambda: Point2D(DEFAULT_SQUARE_SIZE_MM, 0.0))
    rank_vector: Point2D = field(default_factory=lambda: Point2D(0.0, DEFAULT_SQUARE_SIZE_MM))
    z_hover: float = 35.0
    z_down: float = 5.0
    home: Point3D = field(default_factory=lambda: Point3D(0.0, 0.0, 35.0))
    capture_bin: Point3D = field(default_factory=lambda: Point3D(0.0, 0.0, 5.0))
    piece_heights: dict[str, float] = field(
        default_factory=lambda: {piece: 5.0 for piece in PIECE_TYPES}
    )

    @classmethod
    def from_three_squares(
        cls,
        a1: tuple[float, float],
        h1: tuple[float, float],
        a8: tuple[float, float],
        *,
        z_hover: float = 35.0,
        z_down: float = 5.0,
        home: tuple[float, float, float] = (0.0, 0.0, 35.0),
        capture_bin: tuple[float, float, float] = (0.0, 0.0, 5.0),
        piece_heights: dict[str, float] | None = None,
    ) -> "BoardCalibration":
        return cls(
            a1=Point2D(*a1),
            file_vector=Point2D((h1[0] - a1[0]) / 7.0, (h1[1] - a1[1]) / 7.0),
            rank_vector=Point2D((a8[0] - a1[0]) / 7.0, (a8[1] - a1[1]) / 7.0),
            z_hover=z_hover,
            z_down=z_down,
            home=Point3D(*home),
            capture_bin=Point3D(*capture_bin),
            piece_heights=_piece_heights_from_dict(piece_heights, z_down),
        )

    @classmethod
    def from_dict(cls, data: dict) -> "BoardCalibration":
        default = cls()
        return cls(
            a1=_point2d_from_dict(data.get("a1"), default.a1),
            file_vector=_point2d_from_dict(data.get("file_vector"), default.file_vector),
            rank_vector=_point2d_from_dict(data.get("rank_vector"), default.rank_vector),
            z_hover=float(data.get("z_hover", 35.0)),
            z_down=float(data.get("z_down", 5.0)),
            home=_point3d_from_dict(data.get("home"), default.home),
            capture_bin=_point3d_from_dict(data.get("capture_bin"), default.capture_bin),
            piece_heights=_piece_heights_from_dict(
                data.get("piece_heights"),
                float(data.get("z_down", 5.0)),
            ),
        )

    def to_dict(self) -> dict:
        return asdict(self)

    def square_center(self, square: str) -> tuple[float, float]:
        if len(square) != 2 or square[0] < "a" or square[0] > "h" or square[1] < "1" or square[1] > "8":
            raise ValueError(f"Invalid chess square: {square!r}")

        file_index = ord(square[0]) - ord("a")
        rank_index = int(square[1]) - 1
        x = self.a1.x + file_index * self.file_vector.x + rank_index * self.rank_vector.x
        y = self.a1.y + file_index * self.file_vector.y + rank_index * self.rank_vector.y
        return (round(x, 3), round(y, 3))

    def z_for_piece(self, piece_type: str | None = None) -> float:
        if piece_type is None:
            return self.z_down
        normalized = normalize_piece_type(piece_type)
        return float(self.piece_heights.get(normalized, self.z_down))


def normalize_piece_type(piece_type: str) -> str:
    aliases = {
        "p": "pawn",
        "n": "knight",
        "b": "bishop",
        "r": "rook",
        "q": "queen",
        "k": "king",
    }
    key = piece_type.lower().strip()
    return aliases.get(key, key)


def load_calibration(
    path: str | Path = DEFAULT_CONFIG_PATH,
    *,
    require_exists: bool = False,
) -> BoardCalibration:
    config_path = Path(path)
    if not config_path.exists():
        if require_exists:
            raise FileNotFoundError(
                f"Robot calibration file not found: {config_path}. "
                "Run python_code/calibrate_robot.py write first."
            )
        return BoardCalibration()

    with config_path.open("r", encoding="utf-8") as f:
        return BoardCalibration.from_dict(json.load(f))


def _point2d_from_dict(data: dict | None, default: Point2D) -> Point2D:
    if data is None:
        return default
    return Point2D(float(data.get("x", default.x)), float(data.get("y", default.y)))


def _point3d_from_dict(data: dict | None, default: Point3D) -> Point3D:
    if data is None:
        return default
    return Point3D(
        float(data.get("x", default.x)),
        float(data.get("y", default.y)),
        float(data.get("z", default.z)),
    )


def _piece_heights_from_dict(data: dict | None, fallback_z_down: float) -> dict[str, float]:
    values = {piece: float(fallback_z_down) for piece in PIECE_TYPES}
    if data is None:
        return values
    for piece in PIECE_TYPES:
        if piece in data:
            values[piece] = float(data[piece])
    return values


def save_calibration(
    calibration: BoardCalibration,
    path: str | Path = DEFAULT_CONFIG_PATH,
) -> Path:
    config_path = Path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as f:
        json.dump(calibration.to_dict(), f, indent=2)
        f.write("\n")
    return config_path


DEFAULT_CALIBRATION = load_calibration()

Z_HOVER = DEFAULT_CALIBRATION.z_hover
Z_DOWN = DEFAULT_CALIBRATION.z_down
H_X = DEFAULT_CALIBRATION.home.x
H_Y = DEFAULT_CALIBRATION.home.y
H_Z = DEFAULT_CALIBRATION.home.z
T_X = DEFAULT_CALIBRATION.capture_bin.x
T_Y = DEFAULT_CALIBRATION.capture_bin.y
T_Z = DEFAULT_CALIBRATION.capture_bin.z
STEP = DEFAULT_SQUARE_SIZE_MM


def get_square_position(square: str, calibration: BoardCalibration | None = None) -> tuple[float, float]:
    return (calibration or DEFAULT_CALIBRATION).square_center(square)
