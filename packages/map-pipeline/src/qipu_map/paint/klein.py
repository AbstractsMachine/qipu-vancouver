"""The real painter: FLUX.2 klein through diffusers, on a CUDA GPU.

It makes the same call as the live runner: `Flux2KleinPipeline(image=[...], prompt=..., 1024 x 1024, 4 steps, guidance
1.0)`, an edit from pure noise conditioned on the reference images (there is no img2img strength in this pipeline), with
the start latents taken from the world noise field and the generator on the CPU, so a tile comes out the same on any GPU
model.

Needs the `paint` extra (torch, diffusers, transformers, accelerate). The model weights download from Hugging Face on
first use; a gated model reads the token from the HF_TOKEN environment variable, nothing else.
"""

from __future__ import annotations

import os
from typing import Any

import numpy as np
from PIL import Image

from qipu_map.paint.backends import RGB, Request, model_recipe
from qipu_map.paint.noise import CELL_PX, noise_field


class DiffusersKlein:
    """The real painter: FLUX.2 klein through diffusers on a CUDA GPU. Needs the `paint` extra."""

    name = "diffusers"

    def __init__(self, model: str, steps: int, guidance: float) -> None:
        import torch  # noqa: PLC0415 (optional extra)
        from diffusers import Flux2KleinPipeline  # noqa: PLC0415

        self.model, self.steps, self.guidance = model, steps, guidance
        self._torch: Any = torch
        token = os.environ.get("HF_TOKEN") or None
        pipe = Flux2KleinPipeline.from_pretrained(model, torch_dtype=torch.bfloat16, token=token)
        self._pipe: Any = pipe.to("cuda")
        self._pipe.set_progress_bar_config(disable=True)
        self._channels = int(self._pipe.transformer.config.in_channels)

    @property
    def recipe(self) -> str:
        return model_recipe(self.model, self.steps, self.guidance)

    def paint(self, request: Request) -> RGB:
        torch = self._torch
        n = request.size // CELL_PX
        noise = noise_field(
            request.noise_key, request.level, request.x // CELL_PX, request.y // CELL_PX, n=n, channels=self._channels
        )
        latents = torch.from_numpy(noise[None]).to("cuda", dtype=torch.bfloat16)
        out = self._pipe(
            image=[Image.fromarray(im) for im in request.images],
            prompt=request.prompt,
            width=request.size,
            height=request.size,
            num_inference_steps=self.steps,
            guidance_scale=self.guidance,
            latents=latents,
            generator=torch.Generator("cpu").manual_seed(request.seed),
        ).images[0]
        return np.asarray(out.convert("RGB"), dtype=np.uint8)
