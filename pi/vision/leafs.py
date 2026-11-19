#!/usr/bin/env python3
"""Leaf monitoring with the original U2-Net model and colour rules.

Pipeline: photograph -> foreground saliency map -> binary leaf-like regions ->
green/yellow/brown fractions -> a rough condition label.

The split between learned and hand-written stages matters:

  learned      the U2-Net saliency map. It locates prominent foreground pixels.
               It does not predict disease, and there are no class labels or
               softmax anywhere in this path.
  hand-written Otsu threshold, morphology, connected-component filtering, HSV
               colour fractions, and the health rule in helpers.py.

So "healthy-ish" is a colour heuristic, not a diagnosis. Lighting, background,
species and the thresholds all move it.

    python3 leafs.py                                  # bundled healthy sample
    python3 leafs.py --image images/pepper_bacterial_spot.jpg
    python3 leafs.py --camera                         # live Pi camera
    python3 leafs.py --camera --save shot.jpg         # keep the frame too
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

# pi/vision/leafs.py -> pi/vision -> pi, so `common` is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.camera import CameraSettings, capture as camera_capture

from helpers import (
    draw_overlay,
    health_from_colors,
    read_and_resize,
    split_leaf_masks,
)

BASE = Path(__file__).resolve().parent
IMAGE_FILE = "images/pepper_healthy.jpg"

# pi/vision/leafs.py -> pi/vision -> pi -> project root
VISION_PATH = BASE.parents[1] / "config" / "vision.json"

# The provided rule set, used when config/vision.json is missing. Same bands as
# helpers.color_fracs, spelled out so the two can be compared.
DEFAULT_BANDS = {
    "green": {"hue": (35, 85), "sat": 30, "val": 30},
    "yellow": {"hue": (20, 34), "sat": 20, "val": 40},
    "brown": {"hue": (5, 24), "sat": 0, "val": 0, "val_max": 200},
}


def load_bands(path: str | Path | None = None) -> dict:
    """Read the colour bands from config/vision.json.

    Falls back to the provided rule set when the file is absent, so a checkout
    without one behaves exactly as before.
    """
    config_path = Path(path) if path else VISION_PATH
    if not config_path.exists():
        return DEFAULT_BANDS

    data = json.loads(config_path.read_text())
    bands = {}
    for name, default in DEFAULT_BANDS.items():
        entry = data.get(name, {})
        hue = entry.get("hue", default["hue"])
        band = {
            "hue": (int(hue[0]), int(hue[1])),
            "sat": int(entry.get("sat", default["sat"])),
            "val": int(entry.get("val", default["val"])),
        }
        if "val_max" in entry or "val_max" in default:
            band["val_max"] = int(entry.get("val_max", default.get("val_max", 255)))
        bands[name] = band
    return bands


def color_fracs(img_bgr: np.ndarray, mask: np.ndarray, bands: dict) -> dict:
    """Fraction of the masked pixels falling in each colour band.

    Same shape as helpers.color_fracs, but the bands come from config so they
    can be tuned without editing code. The provided bands stop at hue 85, so a
    leaf that reads bluer than that scores zero on all three and the verdict
    falls through to "borderline" with no explanation.
    """
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    inside = mask == 255
    total = float(np.count_nonzero(inside))
    if total == 0:
        return {name: 0.0 for name in bands}

    h = hsv[..., 0][inside]
    s = hsv[..., 1][inside]
    v = hsv[..., 2][inside]

    fractions = {}
    for name, band in bands.items():
        low, high = band["hue"]
        hit = (h >= low) & (h <= high) & (s >= band["sat"]) & (v >= band["val"])
        if "val_max" in band:
            hit &= v <= band["val_max"]
        fractions[name] = float(np.count_nonzero(hit)) / total
    return fractions


def mean_hsv(img_bgr: np.ndarray, mask: np.ndarray) -> tuple[float, float, float]:
    """Median hue, saturation and value inside the mask.

    Median rather than mean because hue wraps at 179, and a leaf with a few
    pixels either side of the wrap would average to something meaningless.
    """
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    inside = mask == 255
    if not np.count_nonzero(inside):
        return (0.0, 0.0, 0.0)
    h, s, v = np.median(hsv[inside], axis=0)
    return (float(h), float(s), float(v))


_SESSION: tuple[ort.InferenceSession, str] | None = None


def load_model() -> tuple[ort.InferenceSession, str]:
    """Return the CPU inference session and its input name.

    One session is created and reused; loading the model per image would
    dominate the runtime. The input name is read from the session rather than
    hard-coded, because the bundled export calls it `input.1`.
    """
    global _SESSION
    if _SESSION is None:
        # The model is not in the repository, so a fresh clone has no vision
        # until someone copies it in. Say that plainly: onnxruntime's own error
        # is a NO_SUCHFILE traceback that gives no hint what to do about it.
        model_path = BASE / "u2netp.onnx"
        if not model_path.exists():
            raise FileNotFoundError(
                f"{model_path} is missing. It is not in the repository because "
                "its provenance is unclear; unzip the course's leafs-starter.zip "
                "and copy u2netp.onnx into pi/vision/. See README.md."
            )
        session = ort.InferenceSession(
            str(model_path), providers=["CPUExecutionProvider"]
        )
        _SESSION = (session, session.get_inputs()[0].name)
    return _SESSION


def prepare_image(image: np.ndarray) -> np.ndarray:
    """Convert a BGR image to float32 RGB with shape (1, 3, 320, 320).

    OpenCV hands us BGR; the network was trained on RGB. Forgetting the swap
    does not crash anything, it just quietly feeds the network the wrong
    channels and the saliency map degrades.
    """
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    resized = cv2.resize(rgb, (320, 320), interpolation=cv2.INTER_AREA)
    pixels = resized.astype(np.float32) / 255.0
    channels_first = pixels.transpose(2, 0, 1)      # HWC -> CHW
    batch = np.expand_dims(channels_first, axis=0)  # CHW -> NCHW
    return np.ascontiguousarray(batch)


def infer_map(session: ort.InferenceSession, input_name: str, image: np.ndarray) -> np.ndarray:
    """Return the first output's 320 x 320 saliency map.

    The model has seven outputs from different stages; the original code uses
    the first. `[0, 0]` drops the batch and channel axes, leaving height and
    width. Higher values favour foreground.
    """
    outputs = session.run(None, {input_name: prepare_image(image)})
    return outputs[0][0, 0]


def make_leaf_masks(saliency: np.ndarray, image: np.ndarray) -> list[np.ndarray]:
    """Return uint8 masks at the working image size, using 0 and 255.

    Min-max scaling is for display contrast, not calibrated confidence. Otsu
    picks the threshold from the histogram, so it is not always 127. Closing
    fills small holes and joins nearby foreground; opening removes specks.
    """
    low, high = saliency.min(), saliency.max()
    scaled = 255 * (saliency - low) / (high - low + 1e-8)
    scaled = scaled.astype(np.uint8)

    height, width = image.shape[:2]
    full_size = cv2.resize(scaled, (width, height), interpolation=cv2.INTER_LINEAR)

    _, binary = cv2.threshold(full_size, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    kernel = np.ones((5, 5), dtype=np.uint8)
    clean = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
    clean = cv2.morphologyEx(clean, cv2.MORPH_OPEN, kernel, iterations=1)

    return split_leaf_masks(clean)


def analyse(
    image: np.ndarray, bands: dict | None = None
) -> tuple[list[np.ndarray], list[dict]]:
    """Run the whole pipeline on one frame.

    Returns the masks and one result per leaf, so a caller that only wants the
    verdict (the V1 loop) does not have to reimplement the pipeline. Each result
    carries the measured HSV as well as the fractions: a verdict with no numbers
    behind it cannot be tuned.
    """
    session, input_name = load_model()
    saliency = infer_map(session, input_name, image)
    masks = make_leaf_masks(saliency, image)
    bands = bands or load_bands()

    results = []
    for number, mask in enumerate(masks, 1):
        fractions = color_fracs(image, mask, bands)
        results.append(
            {
                "number": number,
                "fractions": fractions,
                "hsv": mean_hsv(image, mask),
                "condition": health_from_colors(fractions),
            }
        )
    return masks, results


def annotate(image: np.ndarray, masks: list[np.ndarray], results: list[dict]) -> np.ndarray:
    """The same frame with the leaf regions outlined and the verdicts written on.

    This is the picture that explains the log line. Without it "stressed-ish" is
    just a word, and there is no way to tell a real problem from the model
    having picked the wrong region.
    """
    lines = []
    for r in results:
        fractions = r["fractions"]
        lines.append(f"Leaf {r['number']}: {r['condition']}")
        lines.append(
            f"G={fractions['green']:.2f} "
            f"Y={fractions['yellow']:.2f} "
            f"B={fractions['brown']:.2f}  "
            f"H={r['hsv'][0]:.0f} S={r['hsv'][1]:.0f} V={r['hsv'][2]:.0f}"
        )
    annotated, _ = draw_overlay(image, masks, lines)
    return annotated


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", default=IMAGE_FILE, help="path relative to this folder")
    ap.add_argument("--camera", action="store_true", help="capture from the Pi camera instead")
    ap.add_argument("--camera-config", help="path to camera.json (default: config/camera.json)")
    ap.add_argument("--save", help="write the captured frame here")
    args = ap.parse_args()

    if args.camera:
        settings = CameraSettings.load(args.camera_config)
        image = camera_capture(settings)
        source = (
            f"camera {settings.size[0]}x{settings.size[1]} "
            f"rot={settings.rotation} zoom={settings.zoom:g}"
        )
        if args.save:
            cv2.imwrite(args.save, image)
            print(f"saved frame to {args.save}")
    else:
        image = read_and_resize(str(BASE / args.image))
        source = args.image

    started = time.perf_counter()
    masks, results = analyse(image)
    elapsed = time.perf_counter() - started

    print(f"source: {source}  working size: {image.shape[1]}x{image.shape[0]}")
    print(f"regions: {len(masks)}  pipeline: {elapsed:.2f} s")

    lines = []
    if not results:
        print("No leaf-like regions detected.")
    for result in results:
        fractions = result["fractions"]
        text = (
            f"Leaf {result['number']}: G={fractions['green']:.2f} "
            f"Y={fractions['yellow']:.2f} B={fractions['brown']:.2f} "
            f"{result['condition']}"
        )
        print(text)
        lines.append(text)

    overlay, index_map = draw_overlay(image, masks, lines)
    cv2.imwrite(str(BASE / "leaf_overlay.jpg"), overlay)
    # Saved as uint16 on purpose: a uint8 cast would wrap region IDs above 255.
    cv2.imwrite(str(BASE / "leaf_masks.png"), index_map)
    print("wrote leaf_overlay.jpg and leaf_masks.png")


if __name__ == "__main__":
    main()
