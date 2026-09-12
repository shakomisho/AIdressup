"""Phase 2 engine stub: IDM-VTON (https://github.com/yisol/IDM-VTON).

The class is intentionally complete except for the inference call, so Phase 2 is
a single focused edit. Drop the weights under ``models/idm-vton/`` and install
the heavy deps listed in ``requirements.txt``.

Expected layout::

    models/idm-vton/
      unet/
      unet_encoder/
      image_encoder/
      vae/
      text_encoder/ text_encoder_2/ tokenizer/ tokenizer_2/ scheduler/
      humanparsing/  openpose/        # preprocessing helpers
"""

from __future__ import annotations

import importlib.util
import io

from PIL import Image

from ..config import settings
from .base import EngineUnavailable, TryOnEngine, TryOnInput, TryOnOutput

# Garment category -> IDM-VTON inpainting mask region.
MASK_REGIONS = {
    "shirts": "upper_body",
    "jackets": "upper_body",
    "pants": "lower_body",
    "hats": "head",
    "glasses": "head",
    "shoes": "feet",
}


class IDMVTONEngine(TryOnEngine):
    name = "idm-vton"
    title = "IDM-VTON (diffusion)"
    description = (
        "Diffusion-based try-on. Highest fidelity, ~4-12 s per image on a "
        "consumer GPU. Needs CUDA + ~16 GB VRAM."
    )
    phase = 2
    requires = ["torch", "diffusers", "transformers", "accelerate"]
    execution = "queued"

    def __init__(self) -> None:
        self._pipeline = None

    @property
    def weights_dir(self):
        return settings.models_dir / "idm-vton"

    def is_available(self) -> bool:
        deps_ok = all(importlib.util.find_spec(m) is not None for m in ("torch", "diffusers"))
        return deps_ok and self.weights_dir.is_dir() and any(self.weights_dir.iterdir())

    def unavailable_reason(self) -> str:
        return (
            f"IDM-VTON unavailable. Install {', '.join(self.requires)} and place "
            f"weights in {self.weights_dir}."
        )

    def warmup(self) -> None:
        if self.is_available():
            self._load_pipeline()

    def _load_pipeline(self):
        if self._pipeline is not None:
            return self._pipeline
        if not self.is_available():
            raise EngineUnavailable(self.unavailable_reason())
        # --- Phase 2: replace with the real pipeline -----------------------
        # import torch
        # from src.tryon_pipeline import StableDiffusionXLInpaintPipeline as TryonPipeline
        # self._pipeline = TryonPipeline.from_pretrained(
        #     str(self.weights_dir), torch_dtype=torch.float16
        # ).to("cuda")
        raise EngineUnavailable("IDM-VTON pipeline loader not implemented yet (Phase 2).")

    def generate(self, payload: TryOnInput) -> TryOnOutput:
        pipeline = self._load_pipeline()  # raises EngineUnavailable until Phase 2
        person = Image.open(io.BytesIO(payload.person_image)).convert("RGB")
        garment = Image.open(payload.garment_path).convert("RGB")
        region = MASK_REGIONS.get(payload.garment_category, "upper_body")
        params = payload.params or {}

        result = pipeline(  # pragma: no cover - Phase 2
            image=person,
            cloth=garment,
            mask_region=region,
            num_inference_steps=int(params.get("steps", 30)),
            guidance_scale=float(params.get("guidance_scale", 2.0)),
            seed=int(params.get("seed", 42)),
        ).images[0]

        buf = io.BytesIO()
        result.save(buf, format="PNG")
        return TryOnOutput(buf.getvalue(), meta={"region": region})

    def cache_key_parts(self, payload: TryOnInput) -> list[str]:
        params = payload.params or {}
        return [
            self.name,
            f"steps={params.get('steps', 30)}",
            f"cfg={params.get('guidance_scale', 2.0)}",
            f"seed={params.get('seed', 42)}",
        ]
