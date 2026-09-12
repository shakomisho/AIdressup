"""Phase 2 engine stub: CatVTON (https://github.com/Zheng-Chong/CatVTON).

Lighter than IDM-VTON (~800 M trainable params, runs on ~8 GB VRAM), so it is
the recommended first Phase 2 target. Weights go in ``models/catvton/``.
"""

from __future__ import annotations

import importlib.util
import io

from PIL import Image

from ..config import settings
from .base import EngineUnavailable, TryOnEngine, TryOnInput, TryOnOutput

CLOTH_TYPES = {
    "shirts": "upper",
    "jackets": "upper",
    "pants": "lower",
    "hats": "overall",
    "glasses": "overall",
    "shoes": "overall",
}


class CatVTONEngine(TryOnEngine):
    name = "catvton"
    title = "CatVTON (diffusion, light)"
    description = (
        "Concatenation-based try-on diffusion. ~2-5 s per image, runs on ~8 GB "
        "VRAM. Good default for Phase 2."
    )
    phase = 2
    requires = ["torch", "diffusers", "transformers"]
    execution = "queued"

    def __init__(self) -> None:
        self._pipeline = None

    @property
    def weights_dir(self):
        return settings.models_dir / "catvton"

    def is_available(self) -> bool:
        deps_ok = all(importlib.util.find_spec(m) is not None for m in ("torch", "diffusers"))
        return deps_ok and self.weights_dir.is_dir() and any(self.weights_dir.iterdir())

    def unavailable_reason(self) -> str:
        return (
            f"CatVTON unavailable. Install {', '.join(self.requires)} and place "
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
        # --- Phase 2 -------------------------------------------------------
        # from model.pipeline import CatVTONPipeline
        # self._pipeline = CatVTONPipeline(
        #     base_ckpt="booksforcharlie/stable-diffusion-inpainting",
        #     attn_ckpt=str(self.weights_dir), device="cuda",
        # )
        raise EngineUnavailable("CatVTON pipeline loader not implemented yet (Phase 2).")

    def generate(self, payload: TryOnInput) -> TryOnOutput:
        pipeline = self._load_pipeline()
        person = Image.open(io.BytesIO(payload.person_image)).convert("RGB")
        garment = Image.open(payload.garment_path).convert("RGB")
        params = payload.params or {}

        result = pipeline(  # pragma: no cover - Phase 2
            image=person,
            condition_image=garment,
            cloth_type=CLOTH_TYPES.get(payload.garment_category, "upper"),
            num_inference_steps=int(params.get("steps", 50)),
            guidance_scale=float(params.get("guidance_scale", 2.5)),
        )[0]

        buf = io.BytesIO()
        result.save(buf, format="PNG")
        return TryOnOutput(buf.getvalue())

    def cache_key_parts(self, payload: TryOnInput) -> list[str]:
        params = payload.params or {}
        return [
            self.name,
            f"steps={params.get('steps', 50)}",
            f"cfg={params.get('guidance_scale', 2.5)}",
        ]
