#!/usr/bin/env python3
"""Validate labeled cell images one-by-one.

Walk a folder (recursively), show each matching image, and let you mark it
good or bad with the keyboard:

    SPACE / Y / →   keep (advance)
    X / D / Del     bad  -> move to <root>/.trash/<class>/<relpath>
    Z / ←           undo last action (works for both keep and bad)
    S               skip without recording
    Q / Esc         quit

The filter defaults to "white" (only images whose path contains /white/), so
running the script on a labeled_datasets/<name> folder validates just the white
squares. Use --filter '' to walk everything.

Deletes are non-destructive: bad images are moved into a sibling .trash/
directory that mirrors the original layout. Use --purge after you're happy.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from collections import deque
from pathlib import Path

import cv2
import numpy as np


IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def find_images(root: Path, path_filter: str) -> list[Path]:
    needle = f"/{path_filter}/" if path_filter else ""
    out: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in IMG_EXTS:
            continue
        if ".trash" in p.parts:
            continue
        if needle and needle not in p.as_posix():
            continue
        out.append(p)
    out.sort()
    return out


def mean_brightness(path: Path) -> float | None:
    """Mean L* (perceptual lightness, 0..100) of the image, or None if unreadable."""
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        return None
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    # OpenCV stores L scaled to 0..255; divide to get the canonical 0..100.
    return float(lab[:, :, 0].mean()) * (100.0 / 255.0)


def rank_suspects(
    paths: list[Path], class_hint: str, pct: float, mode: str = "auto"
) -> tuple[list[Path], dict[Path, float]]:
    """Score every image and return (suspects, scores) ordered most-suspect first.

    mode='dark'    -> dimmest first  (find dark pieces inside this class)
    mode='bright'  -> brightest first (find light pieces inside this class)
    mode='outlier' -> furthest from class median first
    mode='auto'    -> 'dark' for white, 'bright' for black, else 'outlier'
    """
    scores: dict[Path, float] = {}
    ls: list[float] = []
    for p in paths:
        b = mean_brightness(p)
        if b is None:
            continue
        scores[p] = b
        ls.append(b)
    if not ls:
        return [], scores
    if mode == "auto":
        hint = class_hint.lower()
        mode = "dark" if hint == "white" else "bright" if hint == "black" else "outlier"
    if mode == "dark":
        ordered = sorted(scores, key=lambda p: scores[p])
    elif mode == "bright":
        ordered = sorted(scores, key=lambda p: -scores[p])
    else:
        median = float(np.median(ls))
        ordered = sorted(scores, key=lambda p: abs(scores[p] - median), reverse=True)
    n = max(1, int(round(len(ordered) * pct / 100.0)))
    return ordered[:n], scores


def render(img: np.ndarray, target: int = 480) -> np.ndarray:
    h, w = img.shape[:2]
    scale = target / max(h, w)
    if scale > 1:
        return cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_NEAREST)
    return img


def overlay(canvas: np.ndarray, lines: list[tuple[str, tuple[int, int, int]]]) -> np.ndarray:
    out = canvas.copy()
    y = 22
    for text, color in lines:
        cv2.putText(out, text, (8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(out, text, (8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1, cv2.LINE_AA)
        y += 22
    return out


def trash_path(root: Path, img: Path) -> Path:
    rel = img.relative_to(root)
    return root / ".trash" / rel


def move(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", type=Path, help="Dataset folder to walk (e.g. labeled_datasets/cnn_combo_data/train)")
    ap.add_argument("--filter", default="white", help="Only show images whose path contains /<filter>/ (default: white). Pass '' for everything.")
    ap.add_argument("--size", type=int, default=480, help="Display size in pixels (default 480)")
    ap.add_argument("--purge", action="store_true", help="Permanently delete <root>/.trash and exit.")
    ap.add_argument("--suspects-only", action="store_true", help="Pre-rank by brightness and only show the most suspect tiles for the class.")
    ap.add_argument("--suspects-pct", type=float, default=15.0, help="Percent of images to treat as suspects (default 15).")
    ap.add_argument("--rank", choices=["auto", "dark", "bright", "outlier"], default="auto",
                    help="How to rank suspects: dark=dimmest first, bright=brightest first, outlier=furthest from median, auto=use class hint.")
    args = ap.parse_args()

    root: Path = args.root.resolve()
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        return 2

    trash_root = root / ".trash"
    if args.purge:
        if trash_root.exists():
            shutil.rmtree(trash_root)
            print(f"Purged {trash_root}")
        else:
            print("No .trash to purge.")
        return 0

    imgs = find_images(root, args.filter)
    if not imgs:
        print(f"No images found under {root} matching filter '{args.filter}'.")
        return 1

    scores: dict[Path, float] = {}
    if args.suspects_only:
        print(f"Scoring {len(imgs)} images by brightness...")
        suspects, scores = rank_suspects(imgs, args.filter, args.suspects_pct, args.rank)
        if not suspects:
            print("No suspects produced (unreadable images?).")
            return 1
        print(f"Reviewing {len(suspects)} most-suspect of {len(imgs)} ({args.suspects_pct:.0f}%) for class '{args.filter}'.")
        imgs = suspects

    print(f"Loaded {len(imgs)} images. Keys: SPACE=keep  X=bad  Z=undo  S=skip  Q=quit")
    win = "validate_labels — SPACE keep / X bad / Z undo / Q quit"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)

    history: deque[tuple[str, Path, Path | None]] = deque()  # (action, original, moved_to)
    idx = 0
    kept = 0
    bad = 0

    while 0 <= idx < len(imgs):
        path = imgs[idx]
        img = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if img is None:
            print(f"Skip unreadable: {path}")
            idx += 1
            continue

        view = render(img, args.size)
        rel = path.relative_to(root).as_posix()
        score_txt = f"  L*={scores[path]:.1f}" if path in scores else ""
        view = overlay(
            view,
            [
                (f"[{idx + 1}/{len(imgs)}]  kept={kept}  bad={bad}{score_txt}", (255, 255, 255)),
                (rel, (200, 220, 255)),
                ("SPACE=keep  X=bad  Z=undo  S=skip  Q=quit", (180, 255, 180)),
            ],
        )
        cv2.imshow(win, view)
        k = cv2.waitKey(0) & 0xFFFF

        # SPACE=32, Y=121, Right arrow on most builds 0x270000 or 83/3
        if k in (32, ord("y"), ord("Y"), 83, 2555904):  # keep
            history.append(("keep", path, None))
            kept += 1
            idx += 1
        elif k in (ord("x"), ord("X"), ord("d"), ord("D"), 8, 127, 3014656):  # bad
            dst = trash_path(root, path)
            move(path, dst)
            history.append(("bad", path, dst))
            bad += 1
            idx += 1
        elif k in (ord("z"), ord("Z"), 81, 2424832):  # undo
            if not history:
                continue
            action, orig, moved = history.pop()
            if action == "bad" and moved is not None and moved.exists():
                move(moved, orig)
                bad -= 1
            elif action == "keep":
                kept -= 1
            idx = max(0, idx - 1)
        elif k in (ord("s"), ord("S")):
            idx += 1
        elif k in (ord("q"), ord("Q"), 27):
            break

    cv2.destroyAllWindows()
    print(f"Done. kept={kept}  bad={bad}  remaining={len(imgs) - idx}")
    if bad:
        print(f"Bad images are in: {trash_root}")
        print(f"  Restore everything: mv {trash_root}/* {root}/  (then rmdir .trash)")
        print(f"  Permanently delete: python {Path(__file__).name} {root} --purge")
    return 0


if __name__ == "__main__":
    sys.exit(main())
