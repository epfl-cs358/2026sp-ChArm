from __future__ import annotations

import warnings
from pathlib import Path
from typing import Callable, Literal

import cv2
import numpy as np

MODELS_DIR = Path(__file__).resolve().parents[4] / "models"
DEFAULT_MODEL_PATH = MODELS_DIR / "piece_color_knn.joblib"
DEFAULT_DATASET_PATH = MODELS_DIR / "piece_color_dataset.npz"

ColorClass = Literal["white", "black"]


def _central_roi(crop: np.ndarray) -> np.ndarray:
    h, w = crop.shape[:2]
    return crop[int(h * 0.2) : int(h * 0.8), int(w * 0.2) : int(w * 0.8)]


def extract_case_features(case_crop_bgr: np.ndarray) -> np.ndarray:
    """
    16-dim feature vector from a preprocessed, warped BGR uint8 case crop.

    Layout:
      [0]  L mean  (LAB, central 60%)
      [1]  L std   (LAB, central 60%)
      [2]  A mean  (LAB, central 60%)
      [3]  B mean  (LAB, central 60%)
      [4]  V mean  (HSV, central 60%)
      [5]  V std   (HSV, central 60%)
      [6]  S mean  (HSV, central 60%)
      [7]  dark/bright pixel ratio in V channel (Otsu threshold on full crop)
      [8-15] V channel histogram, 8 bins, normalized (central 60%)
    """
    assert case_crop_bgr.dtype == np.uint8, "Input must be uint8 BGR"

    roi = _central_roi(case_crop_bgr)

    lab = cv2.cvtColor(roi, cv2.COLOR_BGR2LAB).astype(np.float32)
    L, A, B = lab[:, :, 0], lab[:, :, 1], lab[:, :, 2]

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV).astype(np.float32)
    V, S = hsv[:, :, 2], hsv[:, :, 1]

    # Otsu on full crop V for local dark/bright split
    v_full = cv2.cvtColor(case_crop_bgr, cv2.COLOR_BGR2HSV)[:, :, 2]
    otsu_thresh, _ = cv2.threshold(v_full, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    dark_ratio = float(np.mean(v_full < otsu_thresh))
    bright_ratio = 1.0 - dark_ratio
    dark_bright_ratio = dark_ratio / (bright_ratio + 1e-6)

    hist, _ = np.histogram(V.ravel(), bins=8, range=(0.0, 255.0))
    hist = hist.astype(np.float32) / (hist.sum() + 1e-6)

    base = np.array(
        [
            float(L.mean()),
            float(L.std()),
            float(A.mean()),
            float(B.mean()),
            float(V.mean()),
            float(V.std()),
            float(S.mean()),
            dark_bright_ratio,
        ],
        dtype=np.float32,
    )
    return np.concatenate([base, hist])


def compute_image_median_L(case_crops: list[np.ndarray]) -> float:
    """Median L value across central 60% of all 64 case crops for per-image normalization."""
    medians = []
    for crop in case_crops:
        roi = _central_roi(crop)
        lab = cv2.cvtColor(roi, cv2.COLOR_BGR2LAB)
        medians.append(float(np.median(lab[:, :, 0].astype(np.float32))))
    return float(np.median(medians))


def extract_normalized_features(
    case_crop_bgr: np.ndarray,
    median_L: float,
) -> np.ndarray:
    """Extract features and subtract per-image median L from feature [0] (L mean) only."""
    feats = extract_case_features(case_crop_bgr).copy()
    feats[0] -= median_L
    return feats


AnnotatedImage = dict  # keys: image_id (str), scene_id (str), board_64 (list[str]), image_bgr (np.ndarray)


def build_color_dataset(
    annotated_images: list[AnnotatedImage],
    extract_cells_fn: Callable[[np.ndarray], list[np.ndarray]],
    dataset_path: Path = DEFAULT_DATASET_PATH,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Build (X, y, scene_ids) from annotated images, persisting to dataset_path.

    extract_cells_fn: callable(image_bgr) -> list of 64 preprocessed BGR crops
    Skips cases labeled 'empty'.
    """
    X_list: list[np.ndarray] = []
    y_list: list[str] = []
    scene_list: list[str] = []

    for ann in annotated_images:
        crops = extract_cells_fn(ann["image_bgr"])
        median_L = compute_image_median_L(crops)
        for i, label in enumerate(ann["board_64"]):
            if label not in ("white", "black"):
                continue
            feats = extract_normalized_features(crops[i], median_L)
            X_list.append(feats)
            y_list.append(label)
            scene_list.append(str(ann["scene_id"]))

    X = np.array(X_list, dtype=np.float32)
    y = np.array(y_list)
    scene_ids = np.array(scene_list)

    dataset_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(str(dataset_path), X=X, y=y, scene_ids=scene_ids)
    return X, y, scene_ids


_K_CANDIDATES = (1, 3, 5, 7, 9, 15)


def _select_k(
    X: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray,
    k_candidates: tuple = _K_CANDIDATES,
) -> tuple[int, list[dict]]:
    """
    GroupKFold-5 CV (or LeaveOneGroupOut if <5 groups).
    Parsimony rule: smallest k whose mean F1 is within 1 std of best.
    """
    from sklearn.metrics import f1_score
    from sklearn.model_selection import GroupKFold, LeaveOneGroupOut
    from sklearn.neighbors import KNeighborsClassifier
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    n_groups = len(np.unique(groups))
    if n_groups >= 5:
        cv = GroupKFold(n_splits=5)
        cv_name = "GroupKFold-5"
    else:
        cv = LeaveOneGroupOut()
        cv_name = "LeaveOneGroupOut"
        warnings.warn(
            f"Only {n_groups} scenes — using LeaveOneGroupOut. Add more scenes for reliable k selection.",
            UserWarning,
            stacklevel=2,
        )

    cv_results = []
    for k in k_candidates:
        clf = Pipeline(
            [
                ("scaler", StandardScaler()),
                ("knn", KNeighborsClassifier(n_neighbors=k, weights="distance", metric="euclidean")),
            ]
        )
        fold_scores = []
        for train_idx, val_idx in cv.split(X, y, groups):
            clf.fit(X[train_idx], y[train_idx])
            preds = clf.predict(X[val_idx])
            fold_scores.append(float(f1_score(y[val_idx], preds, average="macro", zero_division=0)))
        mean_f1 = float(np.mean(fold_scores))
        std_f1 = float(np.std(fold_scores))
        cv_results.append({"k": k, "mean_f1": mean_f1, "std_f1": std_f1, "cv": cv_name})

    best_mean = max(r["mean_f1"] for r in cv_results)
    best_std = next(r["std_f1"] for r in cv_results if r["mean_f1"] == best_mean)
    threshold = best_mean - best_std

    for r in sorted(cv_results, key=lambda x: x["k"]):
        if r["mean_f1"] >= threshold:
            return r["k"], cv_results

    return cv_results[-1]["k"], cv_results


def train_color_classifier(
    X: np.ndarray,
    y: np.ndarray,
    scene_ids: np.ndarray,
    model_path: Path = DEFAULT_MODEL_PATH,
) -> dict:
    """
    80/20 scene split, k selection via CV, final fit, save to model_path.
    Returns metrics dict.
    """
    import joblib
    from sklearn.metrics import confusion_matrix, f1_score
    from sklearn.neighbors import KNeighborsClassifier
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    unique_scenes = np.unique(scene_ids)
    rng = np.random.default_rng(seed=42)
    shuffled = rng.permutation(unique_scenes)
    n_train = max(1, int(len(shuffled) * 0.8))
    train_scenes = set(shuffled[:n_train].tolist())
    val_scenes = set(shuffled[n_train:].tolist())

    train_mask = np.array([s in train_scenes for s in scene_ids])
    X_train, y_train = X[train_mask], y[train_mask]
    X_val, y_val = X[~train_mask], y[~train_mask]
    groups_train = scene_ids[train_mask]

    training_warnings = []
    for cls in ("white", "black"):
        count = int(np.sum(y_train == cls))
        if count < 30:
            training_warnings.append(
                f"Only {count} '{cls}' training samples — kNN may be unreliable. Annotate more images."
            )

    best_k, cv_results = _select_k(X_train, y_train, groups_train)

    final_model = Pipeline(
        [
            ("scaler", StandardScaler()),
            ("knn", KNeighborsClassifier(n_neighbors=best_k, weights="distance", metric="euclidean")),
        ]
    )
    final_model.fit(X_train, y_train)

    val_f1 = None
    val_cm = None
    if len(X_val) > 0:
        preds_val = final_model.predict(X_val)
        val_f1 = float(f1_score(y_val, preds_val, average="macro", zero_division=0))
        val_cm = confusion_matrix(y_val, preds_val, labels=["white", "black"]).tolist()

    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(final_model, model_path)

    chosen = next(r for r in cv_results if r["k"] == best_k)
    return {
        "best_k": best_k,
        "cv_results": cv_results,
        "chosen_cv_mean_f1": chosen["mean_f1"],
        "chosen_cv_std_f1": chosen["std_f1"],
        "val_f1": val_f1,
        "val_confusion_matrix": val_cm,
        "n_train": int(len(X_train)),
        "n_val": int(len(X_val)),
        "n_white": int(np.sum(y == "white")),
        "n_black": int(np.sum(y == "black")),
        "n_scenes": int(len(unique_scenes)),
        "n_train_scenes": int(len(train_scenes)),
        "n_val_scenes": int(len(val_scenes)),
        "warnings": training_warnings,
    }


def load_color_model(model_path: Path = DEFAULT_MODEL_PATH):
    """Load sklearn pipeline from disk, or None if not trained yet."""
    import joblib

    if not model_path.exists():
        return None
    return joblib.load(model_path)


def classify_piece_colors(
    case_crops: list[np.ndarray],
    occupancy_mask: list[bool],
    model,
    image_features_context: dict,
) -> list[str]:
    """
    case_crops: list of 64 BGR ndarray
    occupancy_mask: list of 64 bool, True = occupied
    model: loaded sklearn pipeline
    image_features_context: dict with at least {"median_L": float} computed for THIS image

    Returns: list of 64 strings in {"empty", "white", "black"}
    """
    median_L = image_features_context["median_L"]
    occupied_indices = [i for i, occ in enumerate(occupancy_mask) if occ]

    if occupied_indices:
        X = np.array(
            [extract_normalized_features(case_crops[i], median_L) for i in occupied_indices],
            dtype=np.float32,
        )
        preds = model.predict(X)
        pred_map = dict(zip(occupied_indices, preds))
    else:
        pred_map = {}

    return [
        "empty" if not occupancy_mask[i] else pred_map[i]
        for i in range(len(case_crops))
    ]
