# models/

Phase 2 weights live here. Empty in Phase 1 — the landmark overlay engine needs
no model at all (pose tracking runs in the browser via MediaPipe WASM).

The backend reports what is missing at `GET /api/tryon/engines`; the settings
panel greys out engines whose `available` flag is `false`.

```
models/
  catvton/     # recommended first Phase 2 target (~8 GB VRAM)
  idm-vton/    # highest fidelity (~16 GB VRAM)
```

## CatVTON

```bash
pip install torch diffusers transformers accelerate
huggingface-cli download zhengchong/CatVTON --local-dir models/catvton
```

Then implement `_load_pipeline()` in
[`backend/app/tryon/catvton_engine.py`](../backend/app/tryon/catvton_engine.py) —
the commented block shows the exact call. Nothing else changes: the registry,
router, cache and UI already handle it.

## IDM-VTON

```bash
huggingface-cli download yisol/IDM-VTON --local-dir models/idm-vton
```

Expected subfolders: `unet/`, `unet_encoder/`, `image_encoder/`, `vae/`,
`text_encoder{,_2}/`, `tokenizer{,_2}/`, `scheduler/`, plus the `humanparsing/`
and `openpose/` preprocessing helpers.

## Adding a different model

1. Subclass `TryOnEngine` in `backend/app/tryon/`.
2. Implement `is_available()`, `generate()` and (optionally) `cache_key_parts()`.
3. `register(MyEngine())` in `backend/app/tryon/registry.py`.

It appears in the UI engine picker automatically.

## Reality check on latency

Diffusion try-on is **not** real time: 2–12 s per frame on a consumer GPU. The
intended UX is Phase 1 overlay for the live preview, with the AI engine invoked
on demand via the *Generate* button — which is exactly how the stage is wired.
