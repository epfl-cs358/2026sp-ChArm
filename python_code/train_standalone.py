"""Standalone CNN trainer — no project dependencies required.

Usage:
    python train_standalone.py --dataset path/to/dataset [--epochs 40] [--batch-size 64] [--output ./model_out]

Dataset layout expected:
    dataset/
        train/
            black/   *.png or *.jpg
            empty/   *.png or *.jpg
            white/   *.png or *.jpg
        val/
            black/
            empty/
            white/

Install dependencies (once):
    pip install tensorflow matplotlib

On a CUDA GPU Windows machine (TF 2.10 — last native Windows GPU build):
    pip install tensorflow==2.10 matplotlib

On WSL2 / Linux with CUDA:
    pip install tensorflow[and-cuda] matplotlib
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def _build_model(num_classes: int = 3):
    import tensorflow as tf
    from tensorflow.keras import layers, models

    model = models.Sequential([
        layers.Input(shape=(100, 100, 3)),
        layers.RandomFlip("horizontal"),
        layers.RandomRotation(0.2),
        layers.RandomTranslation(0.08, 0.08),
        layers.RandomZoom(0.1),
        layers.RandomBrightness(0.3, value_range=(0, 255)),
        layers.RandomContrast(0.3),
        layers.RandomHue(0.05, value_range=(0, 255)),
        layers.RandomSaturation((0.7, 1.3), value_range=(0, 255)),
        layers.Rescaling(1.0 / 255),
        layers.GaussianNoise(0.02),
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


def _per_class_prf(matrix, class_names) -> dict:
    out: dict = {}
    for i, name in enumerate(class_names):
        tp = float(matrix[i, i])
        fn = float(matrix[i, :].sum() - tp)
        fp = float(matrix[:, i].sum() - tp)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        out[name] = {"precision": precision, "recall": recall, "f1": f1, "support": tp + fn}
    return out


def train(dataset_path: str, output_path: str, epochs: int = 40, batch_size: int = 64) -> None:
    import numpy as np
    import tensorflow as tf

    dataset_dir = Path(dataset_path).resolve()
    train_dir = dataset_dir / "train"
    val_dir = dataset_dir / "val"
    if not train_dir.exists() or not val_dir.exists():
        print(f"ERROR: Expected train/ and val/ inside {dataset_dir}", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(output_path).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Dataset : {dataset_dir}")
    print(f"Output  : {out_dir}")
    gpus = tf.config.list_physical_devices("GPU")
    print(f"GPUs    : {[g.name for g in gpus] if gpus else 'none (CPU only)'}")

    train_ds = tf.keras.utils.image_dataset_from_directory(
        train_dir, image_size=(100, 100), batch_size=batch_size, shuffle=True, seed=42,
    )
    val_ds = tf.keras.utils.image_dataset_from_directory(
        val_dir, image_size=(100, 100), batch_size=batch_size, shuffle=False,
    )

    class_names = list(train_ds.class_names)
    if class_names != list(val_ds.class_names):
        print(f"ERROR: train/val class mismatch: {class_names} vs {list(val_ds.class_names)}", file=sys.stderr)
        sys.exit(1)

    class_to_idx = {name: idx for idx, name in enumerate(class_names)}
    (out_dir / "class_indices.json").write_text(json.dumps(class_to_idx, indent=2))

    counts = {i: 0 for i in range(len(class_names))}
    for cls_name, idx in class_to_idx.items():
        counts[idx] = sum(1 for f in (train_dir / cls_name).iterdir() if f.is_file())
    total = sum(counts.values()) or 1
    class_weights = {
        idx: (total / (len(class_names) * count)) if count > 0 else 0.0
        for idx, count in counts.items()
    }

    print("\nClass distribution (train):")
    for name, idx in class_to_idx.items():
        print(f"  {name:8s}: {counts[idx]:5d} samples  weight={class_weights[idx]:.3f}")

    weight_lookup = tf.constant(
        [class_weights[i] for i in range(len(class_names))], dtype=tf.float32
    )

    def _add_sample_weight(x, y):
        return x, y, tf.gather(weight_lookup, y)

    train_ds = train_ds.map(_add_sample_weight).cache().prefetch(tf.data.AUTOTUNE)
    val_ds_w = val_ds.map(_add_sample_weight).cache().prefetch(tf.data.AUTOTUNE)

    model = _build_model(num_classes=len(class_names))
    model.summary()

    callbacks = [
        tf.keras.callbacks.EarlyStopping(
            monitor="val_loss", patience=4, restore_best_weights=True, verbose=1,
        ),
        tf.keras.callbacks.ReduceLROnPlateau(
            monitor="val_loss", factor=0.5, patience=2, min_lr=1e-5, verbose=1,
        ),
    ]

    history = model.fit(
        train_ds, validation_data=val_ds_w,
        epochs=epochs, callbacks=callbacks, verbose=2,
    )

    model_path = out_dir / "chess_cnn.keras"
    model.save(model_path)
    print(f"\nModel saved → {model_path}")

    history_dict = {k: [float(v) for v in vs] for k, vs in history.history.items()}
    _plot_training_curves(history_dict, out_dir / "training_curves.png")

    y_true, y_pred = [], []
    for batch_x, batch_y in val_ds:
        probs = model.predict(batch_x, verbose=0)
        y_true.extend(int(i) for i in batch_y.numpy())
        y_pred.extend(int(i) for i in probs.argmax(axis=1))

    n = len(class_names)
    matrix = np.zeros((n, n), dtype=np.int64)
    for t, p in zip(y_true, y_pred):
        matrix[t, p] += 1
    _plot_confusion_matrix(matrix, class_names, out_dir / "confusion_matrix.png")

    prf = _per_class_prf(matrix, class_names)
    metrics = {
        "dataset": str(dataset_dir),
        "epochs_run": len(history_dict.get("loss", [])),
        "batch_size": batch_size,
        "class_names": class_names,
        "class_to_idx": class_to_idx,
        "train_acc": history_dict.get("accuracy", [0.0])[-1],
        "val_acc": history_dict.get("val_accuracy", [0.0])[-1],
        "per_class": prf,
        "confusion_matrix": matrix.tolist(),
        "finished_at": time.time(),
    }
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))

    print("\nPer-class results:")
    for cls, m in prf.items():
        print(f"  {cls:8s}  precision={m['precision']:.2f}  recall={m['recall']:.2f}  f1={m['f1']:.2f}")
    print(f"\nVal accuracy: {metrics['val_acc']:.3f}")
    print(f"Outputs in  : {out_dir}")


def main() -> None:
    p = argparse.ArgumentParser(description="Train ChArm chess CNN (standalone)")
    p.add_argument("--dataset", required=True, help="Path to dataset folder (must contain train/ and val/)")
    p.add_argument("--output", default="./model_out", help="Where to write model + artifacts")
    p.add_argument("--epochs", type=int, default=40)
    p.add_argument("--batch-size", type=int, default=64)
    args = p.parse_args()
    train(args.dataset, args.output, args.epochs, args.batch_size)


if __name__ == "__main__":
    main()
