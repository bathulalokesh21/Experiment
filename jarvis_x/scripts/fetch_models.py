"""Download the two camera model files into data\\models (only needed if the bundled copies are missing).
   python scripts\\fetch_models.py
On college Wi-Fi that blocks Google downloads, run this once on a phone hotspot."""
from __future__ import annotations

import ssl
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server import config  # noqa: E402

FILES = {
    "hand_landmarker.task": "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
    "blaze_face_short_range.tflite": "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite",
}


def main() -> int:
    import certifi
    ctx = ssl.create_default_context(cafile=certifi.where())
    target = config.data("models")
    target.mkdir(parents=True, exist_ok=True)
    failed = 0
    for name, url in FILES.items():
        try:
            with urllib.request.urlopen(url, timeout=60, context=ctx) as res:
                data = res.read()
            if len(data) < 100_000:
                raise ValueError("the download is too small to be the model")
            (target / name).write_bytes(data)
            print(f"[ OK ] {name} ({len(data) // 1024} KB)")
        except Exception as exc:
            failed += 1
            print(f"[FAIL] {name}: {type(exc).__name__}: {exc}\n       This network may block Google downloads. Try a phone hotspot.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
