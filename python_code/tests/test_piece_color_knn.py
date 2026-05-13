from __future__ import annotations

import numpy as np
import pytest

from charm.vision.piece_color_knn import (
    classify_piece_colors,
    compute_image_median_L,
    extract_case_features,
    extract_normalized_features,
)


def _make_crop(value: int = 128, size: int = 60) -> np.ndarray:
    """Uniform-color BGR crop of given pixel value."""
    return np.full((size, size, 3), value, dtype=np.uint8)


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


def test_features_shape():
    crop = _make_crop(150)
    feats = extract_case_features(crop)
    assert feats.shape == (16,), f"Expected (16,), got {feats.shape}"
    assert feats.dtype == np.float32


def test_features_invariant_to_global_shift():
    """Adding a constant brightness globally changes raw L mean but not normalized L mean."""
    crop_dark = _make_crop(80)
    crop_bright = _make_crop(80 + 40)

    raw_dark = extract_case_features(crop_dark)
    raw_bright = extract_case_features(crop_bright)

    # Raw L means differ
    assert raw_bright[0] != raw_dark[0]

    # Simulate per-image median normalization with all identical crops
    crops_dark = [crop_dark] * 64
    crops_bright = [crop_bright] * 64

    median_dark = compute_image_median_L(crops_dark)
    median_bright = compute_image_median_L(crops_bright)

    norm_dark = extract_normalized_features(crop_dark, median_dark)
    norm_bright = extract_normalized_features(crop_bright, median_bright)

    # Normalized L mean (feature[0]) should be the same (both are median of their own scene)
    assert abs(norm_dark[0] - norm_bright[0]) < 1e-3, (
        f"Normalized L means differ: {norm_dark[0]:.4f} vs {norm_bright[0]:.4f}"
    )

    # Other features (A, B, S, ...) must NOT be affected by the normalization
    for i in range(2, 14):
        assert abs(norm_dark[i] - raw_dark[i]) < 1e-5


def test_split_no_scene_leak():
    """GroupKFold never puts the same scene_id in both train and val."""
    from sklearn.model_selection import GroupKFold

    n_scenes = 8
    samples_per_scene = 20
    groups = np.repeat(np.arange(n_scenes), samples_per_scene)
    X = np.random.rand(len(groups), 14).astype(np.float32)
    y = np.array(["white" if i % 2 == 0 else "black" for i in range(len(groups))])

    cv = GroupKFold(n_splits=5)
    for train_idx, val_idx in cv.split(X, y, groups):
        train_scenes = set(groups[train_idx].tolist())
        val_scenes = set(groups[val_idx].tolist())
        assert train_scenes.isdisjoint(val_scenes), (
            f"Scene leak detected: {train_scenes & val_scenes}"
        )


def test_inference_handles_empty_cases():
    """classify_piece_colors returns correct length and respects the occupancy mask."""
    from sklearn.neighbors import KNeighborsClassifier
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    # Tiny synthetic model: 2 white + 2 black training samples
    white_crop = _make_crop(200)
    black_crop = _make_crop(30)

    X_train = np.array(
        [extract_case_features(white_crop)] * 2 + [extract_case_features(black_crop)] * 2,
        dtype=np.float32,
    )
    y_train = np.array(["white", "white", "black", "black"])

    model = Pipeline(
        [
            ("scaler", StandardScaler()),
            ("knn", KNeighborsClassifier(n_neighbors=1, weights="distance")),
        ]
    )
    model.fit(X_train, y_train)

    # 64 crops alternating white/empty
    crops = []
    mask = []
    for i in range(64):
        if i % 3 == 0:
            crops.append(black_crop)
            mask.append(True)
        elif i % 3 == 1:
            crops.append(white_crop)
            mask.append(True)
        else:
            crops.append(_make_crop(128))
            mask.append(False)

    median_L = compute_image_median_L(crops)
    result = classify_piece_colors(crops, mask, model, {"median_L": median_L})

    assert len(result) == 64

    for i, (occ, label) in enumerate(zip(mask, result)):
        if not occ:
            assert label == "empty", f"Index {i}: expected 'empty', got '{label}'"
        else:
            assert label in ("white", "black"), f"Index {i}: unexpected label '{label}'"


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------


@pytest.fixture
def fixture_annotated_image():
    """
    Synthetic fixture: 8x8 board where top 4 rows are 'black' pieces on dark crops
    and bottom 4 rows are 'white' pieces on bright crops.
    """
    size = 60
    dark_crop = np.full((size, size, 3), 40, dtype=np.uint8)
    bright_crop = np.full((size, size, 3), 210, dtype=np.uint8)

    crops = []
    board_64 = []
    for r in range(8):
        for c in range(8):
            if r < 4:
                crops.append(dark_crop.copy())
                board_64.append("black")
            else:
                crops.append(bright_crop.copy())
                board_64.append("white")

    # Synthesize a "board image" by tiling crops (not used for feature extraction here)
    board_img = np.zeros((480, 480, 3), dtype=np.uint8)

    return {
        "image_id": "fixture_001",
        "scene_id": "fixture_scene",
        "board_64": board_64,
        "crops": crops,
        "board_img": board_img,
    }


def test_pipeline_end_to_end_on_fixture_image(fixture_annotated_image, tmp_path):
    """Full train + inference cycle on synthetic fixture achieves macro-F1 > 0.9."""
    from sklearn.metrics import f1_score
    from sklearn.model_selection import LeaveOneGroupOut
    from sklearn.neighbors import KNeighborsClassifier
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    from charm.vision.piece_color_knn import build_color_dataset, train_color_classifier

    ann = fixture_annotated_image
    crops = ann["crops"]
    board_64 = ann["board_64"]

    # Use pre-extracted crops directly (bypass pipeline warp)
    def extract_cells_fn(image_bgr):
        return crops  # fixture: crops are pre-prepared

    annotated_images = [
        {
            "image_id": ann["image_id"],
            "scene_id": ann["scene_id"],
            "board_64": board_64,
            "image_bgr": ann["board_img"],
        }
    ]

    dataset_path = tmp_path / "dataset.npz"
    model_path = tmp_path / "model.joblib"

    X, y, scene_ids = build_color_dataset(annotated_images, extract_cells_fn, dataset_path)

    assert X.shape[1] == 16
    assert len(y) == 64  # no empties in this fixture

    # Single scene → can't do train/val split; train on all and check in-sample
    model = Pipeline(
        [
            ("scaler", StandardScaler()),
            ("knn", KNeighborsClassifier(n_neighbors=1, weights="distance")),
        ]
    )
    model.fit(X, y)
    preds = model.predict(X)
    f1 = f1_score(y, preds, average="macro")

    assert f1 > 0.9, f"Expected macro-F1 > 0.9, got {f1:.4f}"
