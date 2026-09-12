#!/usr/bin/env python3
"""Generate placeholder garment PNGs + ``catalog.json`` for ``assets/clothes/``.

These are flat vector-ish silhouettes with transparent backgrounds, drawn at 4x
and downsampled for clean edges. Replace them with real cut-out product photos
whenever you like — the geometry contract is written into ``catalog.json``:

    scale_multiplier  garment PNG width / reference landmark distance
    pivot_x/pivot_y   where the landmark anchor sits inside the PNG (0..1)

Usage:  python scripts/generate_sample_clothes.py [--force]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.models import SLUG_PREFIX, Category  # noqa: E402

SS = 4  # supersampling factor


def canvas(w: int, h: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def finish(img: Image.Image, w: int, h: int) -> Image.Image:
    return img.resize((w, h), Image.LANCZOS)


def s(*vals: float) -> list[float]:
    return [v * SS for v in vals]


def poly(draw: ImageDraw.ImageDraw, pts: list[tuple[float, float]], fill, outline=None) -> None:
    scaled = [(x * SS, y * SS) for x, y in pts]
    draw.polygon(scaled, fill=fill, outline=outline, width=3 * SS if outline else 0)


def shade(color: tuple[int, int, int], factor: float) -> tuple[int, int, int, int]:
    return (*(max(0, min(255, int(c * factor))) for c in color), 255)


# --------------------------------------------------------------------------
# Garments. Each builder returns (image, geometry dict).
# --------------------------------------------------------------------------
def build_tee(color: tuple[int, int, int], long_sleeve: bool = False) -> tuple[Image.Image, dict]:
    W, H = 1000, 1080
    img, d = canvas(W, H)
    body, dark = (*color, 255), shade(color, 0.82)

    shoulder_y, shoulder_l, shoulder_r = 150.0, 270.0, 730.0
    sleeve_end_y = 620.0 if long_sleeve else 430.0
    sleeve_x = 90.0 if long_sleeve else 120.0

    # sleeves
    poly(d, [(shoulder_l, shoulder_y), (sleeve_x + 70, shoulder_y + 40),
             (sleeve_x, sleeve_end_y - 60), (sleeve_x + 150, sleeve_end_y),
             (shoulder_l + 110, shoulder_y + 260)], dark)
    poly(d, [(shoulder_r, shoulder_y), (W - sleeve_x - 70, shoulder_y + 40),
             (W - sleeve_x, sleeve_end_y - 60), (W - sleeve_x - 150, sleeve_end_y),
             (shoulder_r - 110, shoulder_y + 260)], dark)
    # torso
    poly(d, [(shoulder_l, shoulder_y), (420, 210), (580, 210), (shoulder_r, shoulder_y),
             (700, 380), (690, 1010), (310, 1010), (300, 380)], body)
    # collar
    d.ellipse(s(420, 120, 580, 250), fill=(0, 0, 0, 0))
    d.arc(s(415, 115, 585, 255), start=0, end=180, fill=shade(color, 0.6), width=9 * SS)
    # hem + seam hints
    d.line(s(312, 985, 688, 985), fill=shade(color, 0.7), width=5 * SS)

    return finish(img, W, H), {
        "reference": "shoulder_span",
        "shoulder_span_px": shoulder_r - shoulder_l,
        "anchor_px": (W / 2, shoulder_y),
        "width_px": W,
        "height_px": H,
    }


def build_jacket(color: tuple[int, int, int]) -> tuple[Image.Image, dict]:
    W, H = 1100, 1150
    img, d = canvas(W, H)
    body, dark, darker = (*color, 255), shade(color, 0.85), shade(color, 0.65)

    shoulder_y, shoulder_l, shoulder_r = 160.0, 300.0, 800.0
    poly(d, [(shoulder_l, shoulder_y), (120, 250), (70, 760), (250, 800),
             (shoulder_l + 120, shoulder_y + 300)], dark)
    poly(d, [(shoulder_r, shoulder_y), (W - 120, 250), (W - 70, 760), (W - 250, 800),
             (shoulder_r - 120, shoulder_y + 300)], dark)
    poly(d, [(shoulder_l, shoulder_y), (430, 215), (670, 215), (shoulder_r, shoulder_y),
             (790, 400), (780, 1075), (320, 1075), (310, 400)], body)
    # open front + lapels
    d.line(s(550, 250, 550, 1070), fill=darker, width=7 * SS)
    poly(d, [(430, 215), (550, 250), (550, 470), (455, 330)], darker)
    poly(d, [(670, 215), (550, 250), (550, 470), (645, 330)], darker)
    d.ellipse(s(430, 130, 670, 270), fill=(0, 0, 0, 0))
    # pockets
    d.rectangle(s(350, 790, 500, 840), fill=darker)
    d.rectangle(s(600, 790, 750, 840), fill=darker)

    return finish(img, W, H), {
        "reference": "shoulder_span",
        "shoulder_span_px": shoulder_r - shoulder_l,
        "anchor_px": (W / 2, shoulder_y),
        "width_px": W,
        "height_px": H,
    }


def build_pants(color: tuple[int, int, int], shorts: bool = False) -> tuple[Image.Image, dict]:
    W, H = 900, (760 if shorts else 1400)
    img, d = canvas(W, H)
    body, dark = (*color, 255), shade(color, 0.8)

    waist_y, waist_l, waist_r = 70.0, 270.0, 630.0
    hem_y = H - 60.0
    poly(d, [(waist_l, waist_y), (waist_r, waist_y), (waist_r + 40, 380),
             (620, hem_y), (480, hem_y), (450, 520), (420, hem_y), (280, hem_y),
             (waist_l - 40, 380)], body)
    # waistband + fly + crotch seam
    d.rectangle(s(waist_l - 12, waist_y - 30, waist_r + 12, waist_y + 55), fill=dark)
    d.line(s(450, 125, 450, 500), fill=dark, width=5 * SS)
    d.line(s(285, hem_y - 18, 475, hem_y - 18), fill=dark, width=5 * SS)
    d.line(s(485, hem_y - 18, 615, hem_y - 18), fill=dark, width=5 * SS)

    return finish(img, W, H), {
        "reference": "hip_span",
        "hip_span_px": waist_r - waist_l,
        "anchor_px": (W / 2, waist_y + 20),
        "width_px": W,
        "height_px": H,
    }


def build_cap(color: tuple[int, int, int]) -> tuple[Image.Image, dict]:
    W, H = 1000, 620
    img, d = canvas(W, H)
    body, dark = (*color, 255), shade(color, 0.75)

    band_y = 430.0
    # crown (dome + straight sides down to the band)
    d.ellipse(s(220, 90, 780, 442), fill=body)
    d.rectangle(s(220, 280, 780, band_y), fill=body)
    # brim — front-facing cap, so only the lower half of the ellipse shows
    d.pieslice(s(150, band_y - 60, 950, band_y + 110), start=0, end=180, fill=dark)
    # band + top button
    d.rectangle(s(220, band_y - 60, 780, band_y + 12), fill=dark)
    d.ellipse(s(472, 78, 528, 134), fill=dark)

    return finish(img, W, H), {
        "reference": "ear_span",
        # Crown width is what must match head width.
        "crown_px": 560,
        "anchor_px": (W / 2, band_y - 10),
        "width_px": W,
        "height_px": H,
    }


def build_beanie(color: tuple[int, int, int]) -> tuple[Image.Image, dict]:
    W, H = 760, 640
    img, d = canvas(W, H)
    body, dark = (*color, 255), shade(color, 0.78)
    band_y = 470.0
    d.ellipse(s(90, 80, 670, band_y + 120), fill=body)
    d.rectangle(s(90, 300, 670, band_y), fill=body)
    d.rounded_rectangle(s(70, band_y - 70, 690, band_y + 40), radius=40 * SS, fill=dark)
    d.ellipse(s(340, 40, 420, 120), fill=dark)
    return finish(img, W, H), {
        "reference": "ear_span",
        "crown_px": 580,
        "anchor_px": (W / 2, band_y - 20),
        "width_px": W,
        "height_px": H,
    }


def build_sunglasses(
    frame: tuple[int, int, int],
    lens: tuple[int, int, int],
    aviator: bool = False,
    lens_alpha: int = 215,
) -> tuple[Image.Image, dict]:
    """Front-facing frame. The anchor is the bridge centre, which is where the
    eye-line midpoint lands. ``aviator`` swaps the squared Wayfarer lens for a
    teardrop and thins the frame down to a wire."""
    W, H = 900, 380
    img, d = canvas(W, H)
    frame_c, dark = (*frame, 255), shade(frame, 0.7)
    eye_y = 180.0
    inset = 14.0 if aviator else 26.0

    # Temple arms, drawn first so the frame front overlaps them.
    d.rounded_rectangle(s(14, eye_y - 68, 160, eye_y - 30), radius=16 * SS, fill=dark)
    d.rounded_rectangle(s(W - 160, eye_y - 68, W - 14, eye_y - 30), radius=16 * SS, fill=dark)

    # Each lens is an outer shape in the frame colour with an inset tinted fill
    # on top — a fake stroke, so the border thickness is controllable.
    def lens_pair(x0: float, x1: float, inner_edge: float) -> None:
        if aviator:
            # Teardrop: an ellipse whose lower half is narrowed and pulled
            # toward the nose, sampled densely because poly() has no curves.
            cx, cy = (x0 + x1) / 2, eye_y + 6

            def drop(i: float) -> list[tuple[float, float]]:
                rx, ry, steps = (x1 - x0) / 2 - i, 84.0 - i, 56
                pts = []
                for k in range(steps):
                    t = 2 * math.pi * k / steps
                    sx, sy = math.cos(t), math.sin(t)
                    low = max(0.0, sy)          # 0 across the brow, 1 at the base
                    pts.append((
                        cx + rx * sx * (1 - 0.30 * low) + inner_edge * 0.34 * rx * low,
                        cy + ry * sy,
                    ))
                return pts
            poly(d, drop(0), frame_c)
            poly(d, drop(inset), (*lens, lens_alpha))
            return
        def squared(i: float) -> list[tuple[float, float]]:
            lo, hi = x0 + i, x1 - i
            return [
                (lo, eye_y - 85 + i), (hi, eye_y - 85 + i), (hi - 18, eye_y + 50),
                (hi - 70, eye_y + 95 - i), (lo + 70, eye_y + 95 - i), (lo + 18, eye_y + 50),
            ]
        poly(d, squared(0), frame_c)
        poly(d, squared(inset), (*lens, lens_alpha))

    # inner_edge points toward the nose, so the teardrop hangs on the right side
    # of the left lens and the left side of the right one.
    lens_pair(110, 420, -1)
    lens_pair(480, 790, 1)
    # Bridge, then the brow bar across the top of both lenses.
    d.rounded_rectangle(s(400, eye_y - 72, 500, eye_y - 24), radius=14 * SS, fill=frame_c)
    brow, brow_y = (18.0, eye_y - 74) if aviator else (35.0, eye_y - 82)
    d.rounded_rectangle(s(110, brow_y - brow, 790, brow_y + brow), radius=16 * SS, fill=frame_c)

    return finish(img, W, H), {
        "reference": "eye_span",
        # The outer eye corners sit inside the lens edges: a ~140 mm frame spans
        # a ~88 mm outer-canthal distance, so 900 * 88/140.
        "eye_span_px": 566,
        "anchor_px": (W / 2, eye_y),
        "width_px": W,
        "height_px": H,
    }


def build_sneaker(color: tuple[int, int, int]) -> tuple[Image.Image, dict]:
    """Side profile, toe pointing right. Mirrored at render time for the other foot."""
    W, H = 820, 460
    img, d = canvas(W, H)
    body, dark = (*color, 255), shade(color, 0.72)

    ankle_x, ankle_y = 210.0, 150.0
    # upper
    poly(d, [(120, 330), (130, 180), (200, 120), (300, 130), (420, 220),
             (640, 260), (740, 300), (760, 350), (120, 350)], body)
    # collar + heel tab
    poly(d, [(130, 180), (200, 120), (250, 150), (190, 250)], dark)
    # sole
    d.rounded_rectangle(s(100, 330, 780, 410), radius=34 * SS, fill=dark)
    d.line(s(110, 372, 770, 372), fill=(255, 255, 255, 190), width=6 * SS)
    # laces
    for i in range(4):
        x = 300 + i * 58
        d.line(s(x, 170 + i * 14, x + 46, 205 + i * 14), fill=(255, 255, 255, 220), width=5 * SS)

    return finish(img, W, H), {
        "reference": "foot_length",
        # ankle landmark -> toe landmark distance corresponds to this span
        "foot_length_px": 520,
        "anchor_px": (ankle_x, ankle_y + 120),
        "width_px": W,
        "height_px": H,
    }


# --------------------------------------------------------------------------
# Catalog definition
# --------------------------------------------------------------------------
ITEMS: list[dict] = [
    # --- shirts (Phase 1 focus) ---
    {"file": "shirts/white-tee.png", "name": "White Tee", "brand": "Basics",
     "color": "white", "tags": ["tee", "casual"], "build": lambda: build_tee((244, 246, 248))},
    {"file": "shirts/black-tee.png", "name": "Black Tee", "brand": "Basics",
     "color": "black", "tags": ["tee", "casual"], "build": lambda: build_tee((38, 40, 44))},
    {"file": "shirts/indigo-tee.png", "name": "Indigo Tee", "brand": "Northline",
     "color": "indigo", "tags": ["tee"], "build": lambda: build_tee((67, 84, 180))},
    {"file": "shirts/crimson-tee.png", "name": "Crimson Tee", "brand": "Northline",
     "color": "red", "tags": ["tee"], "build": lambda: build_tee((196, 62, 66))},
    {"file": "shirts/sage-longsleeve.png", "name": "Sage Long Sleeve", "brand": "Atelier",
     "color": "green", "tags": ["longsleeve"],
     "build": lambda: build_tee((122, 154, 122), long_sleeve=True)},
    # --- jackets ---
    {"file": "jackets/denim-jacket.png", "name": "Denim Jacket", "brand": "Northline",
     "color": "blue", "tags": ["denim"], "build": lambda: build_jacket((78, 108, 158))},
    {"file": "jackets/olive-bomber.png", "name": "Olive Bomber", "brand": "Atelier",
     "color": "olive", "tags": ["bomber"], "build": lambda: build_jacket((98, 104, 66))},
    # --- pants ---
    {"file": "pants/blue-jeans.png", "name": "Blue Jeans", "brand": "Northline",
     "color": "blue", "tags": ["denim"], "build": lambda: build_pants((72, 98, 148))},
    {"file": "pants/charcoal-chinos.png", "name": "Charcoal Chinos", "brand": "Basics",
     "color": "charcoal", "tags": ["chinos"], "build": lambda: build_pants((74, 78, 84))},
    {"file": "pants/sand-shorts.png", "name": "Sand Shorts", "brand": "Basics",
     "color": "sand", "tags": ["shorts"],
     "build": lambda: build_pants((204, 184, 146), shorts=True)},
    # --- hats ---
    {"file": "hats/navy-cap.png", "name": "Navy Cap", "brand": "Basics",
     "color": "navy", "tags": ["cap"], "build": lambda: build_cap((44, 62, 102))},
    {"file": "hats/grey-beanie.png", "name": "Grey Beanie", "brand": "Atelier",
     "color": "grey", "tags": ["beanie"], "build": lambda: build_beanie((128, 132, 140))},
    # --- glasses ---
    {"file": "glasses/rayban-wayfarer.png", "name": "Ray-Ban Wayfarer", "brand": "Ray-Ban",
     "color": "black", "tags": ["sunglasses", "wayfarer"],
     "build": lambda: build_sunglasses((26, 28, 32), (22, 26, 34))},
    {"file": "glasses/rayban-aviator.png", "name": "Ray-Ban Aviator", "brand": "Ray-Ban",
     "color": "gold", "tags": ["sunglasses", "aviator"],
     "build": lambda: build_sunglasses((196, 160, 78), (84, 62, 38), aviator=True,
                                       lens_alpha=190)},
    # --- shoes ---
    {"file": "shoes/white-sneaker.png", "name": "White Sneakers", "brand": "Runline",
     "color": "white", "tags": ["sneaker"], "build": lambda: build_sneaker((238, 240, 243))},
    {"file": "shoes/black-sneaker.png", "name": "Black Sneakers", "brand": "Runline",
     "color": "black", "tags": ["sneaker"], "build": lambda: build_sneaker((46, 48, 54))},
]

# Anchor tuning per reference type: how much wider than the landmark distance the
# garment should be, plus a nudge along the body axis (units of the reference span).
REFERENCE_TUNING = {
    "shoulder_span": {"anchor_type": "torso", "fit": 1.06, "offset_y": -0.02},
    "hip_span": {"anchor_type": "hips", "fit": 1.08, "offset_y": -0.04},
    "ear_span": {"anchor_type": "head", "fit": 1.12, "offset_y": -0.26},
    "foot_length": {"anchor_type": "feet", "fit": 1.25, "offset_y": -0.12},
    # Frames want no nudge: the eye-line midpoint is already where the bridge sits.
    "eye_span": {"anchor_type": "eyes", "fit": 1.0, "offset_y": 0.0},
}

REFERENCE_KEY = {
    "shoulder_span": "shoulder_span_px",
    "hip_span": "hip_span_px",
    "ear_span": "crown_px",
    "foot_length": "foot_length_px",
    "eye_span": "eye_span_px",
}

# Glasses sit above the face but below a hat brim.
Z_INDEX = {"pants": 5, "shirts": 10, "jackets": 20, "shoes": 25, "glasses": 28, "hats": 30}


def slugify(value: str) -> str:
    out = "".join(c if c.isalnum() else "-" for c in value.lower())
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="overwrite existing PNGs")
    args = parser.parse_args()

    root = settings.clothes_dir
    entries: list[dict] = []
    written = skipped = 0

    for spec in ITEMS:
        rel = Path(spec["file"])
        out_path = root / rel
        out_path.parent.mkdir(parents=True, exist_ok=True)

        image, geom = spec["build"]()
        if out_path.exists() and not args.force:
            skipped += 1
        else:
            image.save(out_path, format="PNG", optimize=True)
            written += 1

        reference = geom["reference"]
        tuning = REFERENCE_TUNING[reference]
        ref_px = geom[REFERENCE_KEY[reference]]
        anchor_x, anchor_y = geom["anchor_px"]
        category = rel.parent.name

        entries.append(
            {
                "slug": f"{SLUG_PREFIX[Category(category)]}-{slugify(rel.stem)}",
                "name": spec["name"],
                "brand": spec.get("brand"),
                "color": spec.get("color"),
                "tags": spec.get("tags", []),
                "anchor_type": tuning["anchor_type"],
                # PNG width expressed in units of the landmark reference distance
                "scale_multiplier": round(
                    geom["width_px"] / ref_px * tuning["fit"], 4
                ),
                "offset_x": 0.0,
                "offset_y": tuning["offset_y"],
                "rotation_offset": 0.0,
                "pivot_x": round(anchor_x / geom["width_px"], 4),
                "pivot_y": round(anchor_y / geom["height_px"], 4),
                "opacity": 1.0,
                "z_index": Z_INDEX.get(category, 10),
            }
        )

    catalog_path = root / "catalog.json"
    catalog_path.write_text(
        json.dumps(
            {
                "$comment": (
                    "Overlay calibration per garment. scale_multiplier = PNG width / "
                    "landmark reference distance (shoulder span, hip span, head width, "
                    "foot length). pivot_* = landmark anchor position inside the PNG."
                ),
                "items": entries,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"{written} PNG written, {skipped} skipped -> {root}")
    print(f"catalog.json: {len(entries)} items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
