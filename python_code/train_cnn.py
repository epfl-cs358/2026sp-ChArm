"""Train the per-cell CNN classifier (empty / white / black).

CLI:
    python train_cnn.py --dataset cnn_<name> [--epochs 20] [--batch-size 32]
                        [--run-id <id>]

Also exposes a `train(...)` function that the FastAPI server uses to run in a
background thread with a per-epoch callback for live progress.

Outputs (all under python_code/models/<run_id>/):
    chess_cnn.keras
    class_indices.json
    training_curves.png
    confusion_matrix.png
    metrics.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parent
SRC_PATH = ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

LABELED_DATASETS_ROOT = ROOT / "labeled_datasets"
MODELS_ROOT = ROOT / "models"


def _build_model(num_classes: int = 3):
    import tensorflow as tf
    from tensorflow.keras import layers, models

    model = models.Sequential([
        layers.Input(shape=(100, 100, 3)),
        layers.Rescaling(1.0 / 255),
        layers.Conv2D(16, 3, padding="same", activation="relu"),
        layers.MaxPooling2D(2),
        layers.Conv2D(32, 3, padding="same", activation="relu"),
        layers.MaxPooling2D(2),
        layers.Conv2D(64, 3, padding="same", activation="relu"),
        layers.GlobalAveragePooling2D(),
        layers.Dense(64, activation="relu"),
        layers.Dropout(0.3),
        layers.Dense(num_classes, activation="softmax"),
    ])
    model.compile(
        optimizer=tf.keras.optimizers.Adam(),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    return model


def _plot_training_curves(history: dict, out_path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    epochs = range(1, len(history.get("loss", [])) + 1)

    axes[0].plot(epochs, history.get("loss", []), label="train")
    axes[0].plot(epochs, history.get("val_loss", []), label="val")
    axes[0].set_title("Loss")
    axes[0].set_xlabel("epoch")
    axes[0].legend()

    axes[1].plot(epochs, history.get("accuracy", []), label="train")
    axes[1].plot(epochs, history.get("val_accuracy", []), label="val")
    axes[1].set_title("Accuracy")
    axes[1].set_xlabel("epoch")
    axes[1].set_ylim(0, 1)
    axes[1].legend()

    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def _plot_confusion_matrix(matrix, class_names, out_path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    fig, ax = plt.subplots(figsize=(5, 4.5))
    im = ax.imshow(matrix, cmap="Blues")
    ax.set_xticks(range(len(class_names)))
    ax.set_yticks(range(len(class_names)))
    ax.set_xticklabels(class_names)
    ax.set_yticklabels(class_names)
    ax.set_xlabel("predicted")
    ax.set_ylabel("true")
    ax.set_title("Validation confusion matrix")
    fig.colorbar(im, ax=ax)
    total = matrix.sum() or 1
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            ax.text(
                j, i, str(int(matrix[i, j])),
                ha="center", va="center",
                color="white" if matrix[i, j] > total / 6 else "black",
                fontsize=11,
            )
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def _per_class_prf(matrix, class_names) -> dict[str, dict[str, float]]:
    """Per-class precision/recall/F1 from a confusion matrix.

    Rows are true labels, columns are predictions — matches the convention in
    _plot_confusion_matrix and sklearn's default.
    """
    out: dict[str, dict[str, float]] = {}
    for i, name in enumerate(class_names):
        tp = float(matrix[i, i])
        fn = float(matrix[i, :].sum() - tp)
        fp = float(matrix[:, i].sum() - tp)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        out[name] = {"precision": precision, "recall": recall, "f1": f1, "support": tp + fn}
    return out


def train(
    dataset: str,
    epochs: int = 20,
    batch_size: int = 32,
    run_id: Optional[str] = None,
    on_epoch_end: Optional[Callable[[dict], None]] = None,
) -> dict:
    """Run training end-to-end and write every artifact under models/<run_id>/.

    The optional `on_epoch_end` callback receives the same shape the API
    polls for: ``{epoch, total_epochs, train_loss, train_acc, val_loss,
    val_acc}``. Called after each epoch end so the wizard can render a live
    chart without polling Keras internals.
    """
    import numpy as np
    import tensorflow as tf

    dataset_dir = LABELED_DATASETS_ROOT / dataset
    train_dir = dataset_dir / "train"
    val_dir = dataset_dir / "val"
    if not train_dir.exists() or not val_dir.exists():
        raise FileNotFoundError(
            f"Expected train/ and val/ under {dataset_dir} — run build-dataset first."
        )

    if run_id is None:
        run_id = time.strftime("%Y%m%d_%H%M%S")
    run_dir = MODELS_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    train_ds = tf.keras.utils.image_dataset_from_directory(
        train_dir,
        image_size=(100, 100),
        batch_size=batch_size,
        shuffle=True,
        seed=42,
    )
    val_ds = tf.keras.utils.image_dataset_from_directory(
        val_dir,
        image_size=(100, 100),
        batch_size=batch_size,
        shuffle=False,
    )

    # CONTRACT (prompt.md): image_dataset_from_directory sorts class names
    # alphabetically — black=0, empty=1, white=2 — so build the mapping
    # explicitly and persist it. Inference re-reads this file; never assume.
    class_names_train = list(train_ds.class_names)
    class_names_val = list(val_ds.class_names)
    if class_names_train != class_names_val:
        raise RuntimeError(
            f"train/val class lists differ: {class_names_train} vs {class_names_val}"
        )
    class_to_idx = {name: idx for idx, name in enumerate(class_names_train)}
    (run_dir / "class_indices.json").write_text(json.dumps(class_to_idx, indent=2))

    train_ds = train_ds.prefetch(tf.data.AUTOTUNE)
    val_ds_prefetched = val_ds.prefetch(tf.data.AUTOTUNE)

    model = _build_model(num_classes=len(class_names_train))

    class _ProgressCallback(tf.keras.callbacks.Callback):
        def on_epoch_end(self, epoch, logs=None):
            logs = logs or {}
            snapshot = {
                "epoch": int(epoch) + 1,
                "total_epochs": int(epochs),
                "train_loss": float(logs.get("loss", 0.0)),
                "train_acc": float(logs.get("accuracy", 0.0)),
                "val_loss": float(logs.get("val_loss", 0.0)),
                "val_acc": float(logs.get("val_accuracy", 0.0)),
            }
            if on_epoch_end is not None:
                try:
                    on_epoch_end(snapshot)
                except Exception:
                    pass

    history = model.fit(
        train_ds,
        validation_data=val_ds_prefetched,
        epochs=epochs,
        callbacks=[_ProgressCallback()],
        verbose=2,
    )

    # ----- artifacts -----
    model_path = run_dir / "chess_cnn.keras"
    model.save(model_path)

    history_dict = {k: [float(v) for v in vs] for k, vs in history.history.items()}
    _plot_training_curves(history_dict, run_dir / "training_curves.png")

    # Confusion matrix on the held-out val set.
    y_true: list[int] = []
    y_pred: list[int] = []
    for batch_x, batch_y in val_ds:
        probs = model.predict(batch_x, verbose=0)
        y_true.extend([int(i) for i in batch_y.numpy()])
        y_pred.extend([int(i) for i in probs.argmax(axis=1)])

    n = len(class_names_train)
    matrix = np.zeros((n, n), dtype=np.int64)
    for t, p in zip(y_true, y_pred):
        matrix[t, p] += 1
    _plot_confusion_matrix(matrix, class_names_train, run_dir / "confusion_matrix.png")

    prf = _per_class_prf(matrix, class_names_train)
    final_train_acc = history_dict.get("accuracy", [0.0])[-1] if history_dict.get("accuracy") else 0.0
    final_val_acc = history_dict.get("val_accuracy", [0.0])[-1] if history_dict.get("val_accuracy") else 0.0

    metrics = {
        "run_id": run_id,
        "dataset": dataset,
        "epochs": int(epochs),
        "batch_size": int(batch_size),
        "class_names": class_names_train,
        "class_to_idx": class_to_idx,
        "train_acc": final_train_acc,
        "val_acc": final_val_acc,
        "per_class": prf,
        "confusion_matrix": matrix.tolist(),
        "history": history_dict,
        "finished_at": time.time(),
    }
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))
    return metrics


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train ChArm per-cell CNN classifier")
    p.add_argument("--dataset", required=True, help="cnn_<name> subdir of labeled_datasets/")
    p.add_argument("--epochs", type=int, default=20)
    p.add_argument("--batch-size", type=int, default=32)
    p.add_argument("--run-id", default=None, help="Override the run_id; default = YYYYmmdd_HHMMSS")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    metrics = train(
        dataset=args.dataset,
        epochs=args.epochs,
        batch_size=args.batch_size,
        run_id=args.run_id,
    )
    print(json.dumps({
        "run_id": metrics["run_id"],
        "val_acc": metrics["val_acc"],
        "train_acc": metrics["train_acc"],
        "per_class": metrics["per_class"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
