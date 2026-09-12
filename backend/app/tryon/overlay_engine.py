"""Phase 1 engine: landmark-driven PNG compositing (no neural network).

This is the server-side twin of ``frontend/src/lib/anchors.ts``. The browser
does the real-time 30+ FPS overlay on a canvas; this engine reproduces the same
transform with Pillow so that snapshots, exports and API consumers get an
identical image without a webcam.
"""

from __future__ import annotations

import io
import math
from pathlib import Path

from PIL import Image

from .base import TryOnEngine, TryOnInput, TryOnOutput

# MediaPipe Pose (BlazePose 33-point) indices we care about.
L_EYE_OUTER, R_EYE_OUTER = 3, 6
L_EAR, R_EAR = 7, 8
L_SHOULDER, R_SHOULDER = 11, 12
L_HIP, R_HIP = 23, 24
L_KNEE, R_KNEE = 25, 26
L_ANKLE, R_ANKLE = 27, 28
L_FOOT, R_FOOT = 31, 32


def _points(pose: dict | None) -> list[dict] | None:
    if not pose:
        return None
    pts = pose.get("landmarks") or pose.get("poseLandmarks")
    if isinstance(pts, list) and len(pts) >= 33:
        return pts
    return None


def _xy(pts: list[dict], index: int, w: int, h: int) -> tuple[float, float]:
    p = pts[index]
    return float(p["x"]) * w, float(p["y"]) * h


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _mid(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    return (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0


class Placement:
    __slots__ = ("cx", "cy", "width", "angle", "mirror")

    def __init__(
        self, cx: float, cy: float, width: float, angle: float, mirror: bool = False
    ) -> None:
        self.cx, self.cy, self.width, self.angle = cx, cy, width, angle
        self.mirror = mirror


def _norm(v: tuple[float, float]) -> tuple[float, float]:
    length = math.hypot(v[0], v[1]) or 1.0
    return v[0] / length, v[1] / length


def _axis_angle(up: tuple[float, float]) -> float:
    """Degrees of clockwise roll for a garment whose PNG points up."""
    return math.degrees(math.atan2(up[0], -up[1]))


def _place(
    anchor: tuple[float, float],
    up: tuple[float, float],
    span: float,
    scale_multiplier: float,
    offset_x: float,
    offset_y: float,
    rotation_offset: float,
    mirror: bool = False,
) -> Placement:
    """Offsets are applied in the body frame: +x = the subject's right on
    screen, +y = down the body axis. That keeps tuning stable when the person
    leans or the video is mirrored."""
    right = (-up[1], up[0])
    dx = span * (offset_x * right[0] - offset_y * up[0])
    dy = span * (offset_x * right[1] - offset_y * up[1])
    return Placement(
        anchor[0] + dx,
        anchor[1] + dy,
        span * scale_multiplier,
        _wrap(_axis_angle(up) + rotation_offset),
        mirror,
    )


def solve_placements(
    pts: list[dict],
    frame_w: int,
    frame_h: int,
    anchor_type: str,
    scale_multiplier: float,
    offset_x: float,
    offset_y: float,
    rotation_offset: float,
) -> list[Placement]:
    """Return one placement per garment instance (shoes yield two).

    Orientation comes from the *body axis* (hips -> shoulders), never from the
    left/right landmark order, so a mirrored selfie feed renders identically.
    """
    p = lambda i: _xy(pts, i, frame_w, frame_h)  # noqa: E731

    if anchor_type == "torso":
        shoulders = _mid(p(L_SHOULDER), p(R_SHOULDER))
        hips = _mid(p(L_HIP), p(R_HIP))
        span = max(_dist(p(L_SHOULDER), p(R_SHOULDER)), 1.0)
        up = _norm((shoulders[0] - hips[0], shoulders[1] - hips[1]))
        return [
            _place(shoulders, up, span, scale_multiplier, offset_x, offset_y, rotation_offset)
        ]

    if anchor_type == "hips":
        hips = _mid(p(L_HIP), p(R_HIP))
        knees = _mid(p(L_KNEE), p(R_KNEE))
        span = max(_dist(p(L_HIP), p(R_HIP)), 1.0)
        # Legs point down, so the garment "up" is hips -> away from the knees.
        up = _norm((hips[0] - knees[0], hips[1] - knees[1]))
        return [_place(hips, up, span, scale_multiplier, offset_x, offset_y, rotation_offset)]

    if anchor_type == "head":
        ears = _mid(p(L_EAR), p(R_EAR))
        shoulders = _mid(p(L_SHOULDER), p(R_SHOULDER))
        span = max(_dist(p(L_EAR), p(R_EAR)), 1.0)
        up = _norm((ears[0] - shoulders[0], ears[1] - shoulders[1]))
        return [_place(ears, up, span, scale_multiplier, offset_x, offset_y, rotation_offset)]

    if anchor_type == "eyes":
        a, b = p(L_EYE_OUTER), p(R_EYE_OUTER)
        eyes = _mid(a, b)
        shoulders = _mid(p(L_SHOULDER), p(R_SHOULDER))
        span = max(_dist(a, b), 1.0)
        # Roll comes from the eye line, which tracks a tilted head far better
        # than ears -> shoulders does. The eye line is an *undirected* axis, so
        # its perpendicular has two candidates; pick the one pointing away from
        # the shoulders. That choice is mirror-invariant, where relying on the
        # left/right landmark order would flip the frames upside down in a
        # selfie feed.
        axis = _norm((a[0] - b[0], a[1] - b[1]))
        up = (axis[1], -axis[0])
        body_up = (eyes[0] - shoulders[0], eyes[1] - shoulders[1])
        if up[0] * body_up[0] + up[1] * body_up[1] < 0:
            up = (-up[0], -up[1])
        return [_place(eyes, up, span, scale_multiplier, offset_x, offset_y, rotation_offset)]

    if anchor_type == "feet":
        # One placement per foot. The PNG points toe-right; when the toe is left
        # of the ankle the sprite is mirrored rather than rotated 180 degrees.
        out: list[Placement] = []
        for ankle_i, foot_i in ((L_ANKLE, L_FOOT), (R_ANKLE, R_FOOT)):
            ankle, toe = p(ankle_i), p(foot_i)
            span = max(_dist(ankle, toe), 1.0)
            mirror = toe[0] < ankle[0]
            forward = _norm((toe[0] - ankle[0], toe[1] - ankle[1]))
            if mirror:
                forward = (-forward[0], forward[1])
            # A shoe PNG's "up" is perpendicular to its toe direction.
            up = (forward[1], -forward[0])
            flip = -1.0 if mirror else 1.0
            out.append(
                _place(
                    ankle, up, span, scale_multiplier,
                    offset_x * flip, offset_y, rotation_offset * flip, mirror,
                )
            )
        return out

    raise ValueError(f"unknown anchor type: {anchor_type!r}")


def _wrap(deg: float) -> float:
    return ((deg + 180.0) % 360.0) - 180.0


def composite(
    person: Image.Image,
    garment: Image.Image,
    placements: list[Placement],
    pivot_x: float,
    pivot_y: float,
    opacity: float,
) -> Image.Image:
    canvas = person.convert("RGBA")
    for place in placements:
        scale = place.width / garment.width
        target = (
            max(1, int(round(garment.width * scale))),
            max(1, int(round(garment.height * scale))),
        )
        layer = garment.resize(target, Image.LANCZOS)
        if place.mirror:
            layer = layer.transpose(Image.FLIP_LEFT_RIGHT)
        if opacity < 1.0:
            alpha = layer.getchannel("A").point(lambda v: int(v * opacity))
            layer.putalpha(alpha)
        if abs(place.angle) > 0.1:
            layer = layer.rotate(-place.angle, resample=Image.BICUBIC, expand=True)
        # Align the garment pivot with the landmark anchor (mirrored sprites use
        # the mirrored pivot so the heel stays on the ankle).
        pvx = (1.0 - pivot_x) if place.mirror else pivot_x
        px = place.cx - layer.width * pvx
        py = place.cy - layer.height * pivot_y
        canvas.alpha_composite(layer, dest=(int(round(px)), int(round(py))))
    return canvas


class OverlayEngine(TryOnEngine):
    name = "overlay"
    title = "Landmark overlay (Phase 1)"
    description = (
        "Composites the garment PNG onto the frame using MediaPipe Pose landmarks. "
        "Real time, no GPU, no model weights."
    )
    phase = 1
    requires = ["Pillow"]

    def generate(self, payload: TryOnInput) -> TryOnOutput:
        person = Image.open(io.BytesIO(payload.person_image)).convert("RGBA")
        pts = _points(payload.pose_landmarks)
        params = payload.params or {}

        if pts is None:
            # No landmarks: return the frame untouched rather than guessing.
            buf = io.BytesIO()
            person.save(buf, format="PNG")
            return TryOnOutput(buf.getvalue(), meta={"placed": 0, "reason": "no_landmarks"})

        garment = Image.open(payload.garment_path).convert("RGBA")
        placements = solve_placements(
            pts,
            person.width,
            person.height,
            params.get("anchor_type", "torso"),
            float(params.get("scale_multiplier", 1.0)),
            float(params.get("offset_x", 0.0)),
            float(params.get("offset_y", 0.0)),
            float(params.get("rotation_offset", 0.0)),
        )
        result = composite(
            person,
            garment,
            placements,
            float(params.get("pivot_x", 0.5)),
            float(params.get("pivot_y", 0.08)),
            float(params.get("opacity", 1.0)),
        )
        buf = io.BytesIO()
        result.save(buf, format="PNG")
        return TryOnOutput(buf.getvalue(), meta={"placed": len(placements)})

    def cache_key_parts(self, payload: TryOnInput) -> list[str]:
        params = payload.params or {}
        keys = ("anchor_type", "scale_multiplier", "offset_x", "offset_y",
                "rotation_offset", "pivot_x", "pivot_y", "opacity")
        return [self.name, *(f"{k}={params.get(k)}" for k in keys)]


def load_garment(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")
