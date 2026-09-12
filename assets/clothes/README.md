# assets/clothes/

The catalog is just a folder. Drop a transparent PNG (or WebP) into a category
subfolder, hit **Sync** in the sidebar (or `POST /api/clothing/sync`), and it
appears in the UI.

```
assets/clothes/
  shirts/   pants/   jackets/   hats/   glasses/   shoes/
  catalog.json     # optional per-item overrides
  .thumbs/         # generated, git-ignored
```

The bundled PNGs are placeholders drawn by
`backend/scripts/generate_sample_clothes.py`. Replace them with real cut-outs.

## Garment art requirements

- Transparent background, garment only.
- Front-facing and upright — except **shoes**, which are drawn in side profile
  with the **toe pointing right** (the renderer mirrors it for the other foot).
- No perspective skew; the overlay applies rotation and uniform scale only.

## catalog.json

Each entry calibrates one garment. `slug` is `<category-prefix>-<filename>`,
e.g. `shirts/white-tee.png` → `shirt-white-tee`. The prefixes are spelled out in
`SLUG_PREFIX` in `backend/app/models.py`, because de-pluralising `glasses`
mechanically would give `glasse`.

```jsonc
{
  "items": [
    {
      "slug": "shirt-white-tee",
      "name": "White Tee",
      "brand": "Basics",
      "color": "white",
      "tags": ["tee", "casual"],
      "anchor_type": "torso",      // torso | hips | head | eyes | feet
      "scale_multiplier": 2.41,    // PNG width / reference landmark distance
      "offset_x": 0.0,             // body-frame nudge, in units of that distance
      "offset_y": -0.02,           // + is down the body axis
      "rotation_offset": 0.0,      // degrees
      "pivot_x": 0.5,              // where the anchor sits inside the PNG (0..1)
      "pivot_y": 0.139,
      "opacity": 1.0,
      "z_index": 10                // draw order: pants 5, shirts 10, jackets 20,
                                   //             shoes 25, glasses 28, hats 30
    }
  ]
}
```

The reference distance per anchor type:

| anchor_type | reference distance | anchor point |
| --- | --- | --- |
| `torso` | shoulder-to-shoulder | midpoint of the shoulders |
| `hips` | hip-to-hip | midpoint of the hips |
| `head` | ear-to-ear | midpoint of the ears |
| `eyes` | outer eye corner to outer eye corner | midpoint of the eyes |
| `feet` | ankle-to-toe | the ankle (rendered per foot) |

`eyes` takes its roll from the eye line itself rather than from the body axis,
which tracks a tilted head much more closely — the right choice for glasses,
where a couple of degrees of error is visible.

Calibrating a new garment: eyeball it with the **Fit** sliders in the settings
panel, then bake the values you liked into `catalog.json` (or `PATCH
/api/clothing/{id}`, which writes them straight to the database).
