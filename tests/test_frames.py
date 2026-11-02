# /// script
# requires-python = ">=3.10"
# dependencies = ["opencv-python-headless>=4.9", "numpy>=1.26"]
# ///
"""Smoke test for the screenshot-candidate heuristics. No network involved.

    uv run tests/test_frames.py

Builds a synthetic clip out of the three things `extract_candidates` has to tell apart -
flat graphic cards, lit talking-head shots, and a long segment that only completes near
its end - then checks that each survives as its own candidate with the right `kind`.

Two things this test learned the hard way, worth keeping in mind before changing the
thresholds in vault.py:

* Pixel noise does NOT stand in for a talking head. Averaged down to 64x36 it collapses
  to flat grey and is classified as a card. What makes a real shot high-variance is
  large bright and dark regions, not per-pixel detail.
* Three slides whose only difference is ONE/TWO/THREE collapse into a single candidate
  at the 17x16 hash scale. That is intended: the skill tells Claude to drop cards that
  merely repeat a heading. Cards that differ in layout stay distinct, which is what the
  256-bit hash buys over a 64-bit one.
"""
import sys
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "vault"))
import vault as V  # noqa: E402

out = REPO / "tests" / "_out"
out.mkdir(parents=True, exist_ok=True)
video = out / "synthetic.mp4"

W, H, FPS = 640, 360, 30
rng = np.random.default_rng(7)
writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
if not writer.isOpened():
    sys.exit("could not open VideoWriter - is this build of OpenCV missing the mp4v encoder?")


def card(lines, seconds, y0=90, bar=None):
    """Flat light frame with text: what a graphic or text card looks like."""
    f = np.full((H, W, 3), 245, dtype=np.uint8)
    if bar:
        cv2.rectangle(f, bar[0], bar[1], (60, 110, 190), -1)
    for i, (text, scale) in enumerate(lines):
        cv2.putText(f, text, (40, y0 + i * 60), cv2.FONT_HERSHEY_SIMPLEX, scale,
                    (20, 20, 20), 3, cv2.LINE_AA)
    for _ in range(int(seconds * FPS)):
        writer.write(f)


def shot(cx, seconds):
    """A lit subject against a dim room: the large-scale contrast of a real shot."""
    f = np.full((H, W, 3), 38, dtype=np.uint8)
    cv2.ellipse(f, (cx, H // 2), (90, 130), 0, 0, 360, (210, 200, 195), -1)
    cv2.ellipse(f, (cx, H // 2 + 150), (160, 90), 0, 0, 360, (90, 85, 80), -1)
    f = cv2.add(f, rng.integers(0, 12, (H, W, 3), dtype=np.uint8))  # sensor grain
    for _ in range(int(seconds * FPS)):
        writer.write(f)


def whiteboard(seconds):
    """One long segment whose content is only complete near the end."""
    f = np.full((H, W, 3), 250, dtype=np.uint8)
    n = int(seconds * FPS)
    for i in range(n):
        g = f.copy()
        for k in range(int((i / n) * 9)):
            cv2.line(g, (60 + k * 60, 80), (60 + k * 60, 280), (30, 30, 30), 6)
        writer.write(g)


card([("THE THREE PILLARS", 1.1)], 6, y0=180)
shot(220, 8)
card([("1. Networking", 0.9), ("2. Societies and talks", 0.9), ("3. Critical thinking", 0.9)], 6)
shot(300, 8)
whiteboard(12)
card([("Exposure by occupation", 0.8), ("  translators     76%", 0.7),
      ("  mathematicians 100%", 0.7), ("  auditors       100%", 0.7)], 6,
     bar=((380, 60), (600, 300)))
writer.release()
print(f"[test] synthetic clip: {video.name}, {video.stat().st_size // 1024} KiB")

cands, sheets = V.extract_candidates(video, out, interval=1.5, change_t=40, dup_t=18,
                                     min_samples=2, cluster_t=48, dup_plain=60)

print("\n[test] candidates:")
for c in cands:
    print(f"  #{c['id']:<3} {c['ts']:>6}  kind={c['kind']:<5} std={c['std']:<6} dur={c['dur']}")

cards = [c for c in cands if c["kind"] == "card"]
shots = [c for c in cands if c["kind"] == "shot"]
sheet_files = sorted((out / "sheets").glob("*.jpg"))
print(f"\n[test] cards={len(cards)} shots={len(shots)} sheets={len(sheet_files)}")

problems = []
if len(cands) < 6:
    problems.append(f"expected the 6 distinct segments to survive, got {len(cands)}")
if len(cards) < 3:
    problems.append(f"expected at least 3 flat cards, got {len(cards)} - distinct layouts "
                    "on the same light background are being deduplicated")
if len(shots) < 2:
    problems.append(f"expected at least 2 talking-head shots, got {len(shots)}")
if not sheet_files:
    problems.append("no contact sheet was written")
for s in sheet_files:
    if s.stat().st_size < 2000:
        problems.append(f"contact sheet looks empty: {s.name}")

print("\n[test] RESULT: " + ("FAIL - " + "; ".join(problems) if problems else "PASS"))
sys.exit(1 if problems else 0)
