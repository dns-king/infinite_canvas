from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .coords import deterministic_tile_seed
from .generators import NeighborImages, TileGenerationContext, TileGenerator, _blend_context_edges


@dataclass
class DiffusionRuntime:
    pipe: object
    torch: object
    device: str


class StableDiffusionInfinitePipeline(TileGenerator):
    """Context-frame inpainting wrapper for InfiniteDiffusion-style lazy tiles.

    The practical trick here is to inpaint a larger canvas where already generated
    neighbor edges are visible to the model and only the center tile is masked.
    Diffusers keeps the context image in the denoising loop, then this wrapper
    crops and blends the center tile for terrain use.
    """

    def __init__(
        self,
        model_id: str,
        inpaint_model_id: str,
        negative_prompt: str,
        steps: int,
        guidance_scale: float,
        device: str = "auto",
    ) -> None:
        self.model_id = model_id
        self.inpaint_model_id = inpaint_model_id
        self.negative_prompt = negative_prompt
        self.steps = steps
        self.guidance_scale = guidance_scale
        self.device = device
        self._runtime: DiffusionRuntime | None = None

    def generate(self, ctx: TileGenerationContext) -> Image.Image:
        runtime = self._load_runtime()
        canvas, mask = self._build_context_canvas(ctx.neighbors, ctx.size, ctx.context_px)
        generator = runtime.torch.Generator(device=runtime.device).manual_seed(
            deterministic_tile_seed(ctx.x, ctx.y, ctx.seed)
        )
        prompt = (
            f"{ctx.effective_prompt}, top-down terrain texture, coherent aerial landscape, "
            "natural continuation across the image, no border"
        )

        result = runtime.pipe(
            prompt=prompt,
            negative_prompt=self.negative_prompt,
            image=canvas,
            mask_image=mask,
            generator=generator,
            num_inference_steps=self.steps,
            guidance_scale=self.guidance_scale,
            width=canvas.width,
            height=canvas.height,
        ).images[0]

        c = ctx.context_px
        tile = result.crop((c, c, c + ctx.size, c + ctx.size)).resize((ctx.size, ctx.size), Image.Resampling.LANCZOS)
        return _blend_context_edges(tile, ctx.neighbors, ctx.context_px)

    def _load_runtime(self) -> DiffusionRuntime:
        if self._runtime is not None:
            return self._runtime

        try:
            import torch
            from diffusers import StableDiffusionInpaintPipeline
        except ImportError as exc:
            raise RuntimeError(
                "Diffusers mode requires torch and diffusers. Install backend GPU dependencies "
                "or run with INFINITE_CANVAS_GENERATOR=procedural."
            ) from exc

        if self.device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            device = self.device

        dtype = torch.float16 if device == "cuda" else torch.float32
        pipe = StableDiffusionInpaintPipeline.from_pretrained(
            self.inpaint_model_id,
            torch_dtype=dtype,
            safety_checker=None,
            requires_safety_checker=False,
        )
        if device == "cuda":
            pipe = pipe.to(device)
            try:
                pipe.enable_model_cpu_offload()
            except Exception:
                pass
            try:
                pipe.enable_vae_slicing()
            except Exception:
                pass
        else:
            pipe = pipe.to(device)

        self._runtime = DiffusionRuntime(pipe=pipe, torch=torch, device=device)
        return self._runtime

    def _build_context_canvas(
        self,
        neighbors: NeighborImages,
        tile_size: int,
        context_px: int,
    ) -> tuple[Image.Image, Image.Image]:
        canvas_size = tile_size + context_px * 2
        canvas = Image.new("RGB", (canvas_size, canvas_size), (92, 106, 93))
        self._paint_placeholder(canvas)

        c = context_px
        if "left" in neighbors:
            strip = neighbors["left"].resize((tile_size, tile_size)).crop((tile_size - c, 0, tile_size, tile_size))
            canvas.paste(strip, (0, c))
        if "right" in neighbors:
            strip = neighbors["right"].resize((tile_size, tile_size)).crop((0, 0, c, tile_size))
            canvas.paste(strip, (c + tile_size, c))
        if "top" in neighbors:
            strip = neighbors["top"].resize((tile_size, tile_size)).crop((0, tile_size - c, tile_size, tile_size))
            canvas.paste(strip, (c, 0))
        if "bottom" in neighbors:
            strip = neighbors["bottom"].resize((tile_size, tile_size)).crop((0, 0, tile_size, c))
            canvas.paste(strip, (c, c + tile_size))

        mask = Image.new("L", (canvas_size, canvas_size), 0)
        draw = ImageDraw.Draw(mask)
        feather = max(12, context_px // 5)
        draw.rectangle((c, c, c + tile_size, c + tile_size), fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(radius=feather * 0.35))
        return canvas, mask

    def _paint_placeholder(self, canvas: Image.Image) -> None:
        arr = np.zeros((canvas.height, canvas.width, 3), dtype=np.uint8)
        yy, xx = np.mgrid[0 : canvas.height, 0 : canvas.width]
        wave = (np.sin(xx / 23.0) + np.cos(yy / 29.0) + np.sin((xx + yy) / 47.0)) / 3.0
        arr[..., 0] = np.uint8(92 + wave * 18)
        arr[..., 1] = np.uint8(111 + wave * 20)
        arr[..., 2] = np.uint8(96 + wave * 16)
        canvas.paste(Image.fromarray(arr, "RGB"))

