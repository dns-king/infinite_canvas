# InfiniteCanvas Backend

FastAPI tile server for InfiniteCanvas. The default generator is deterministic and procedural so the app can run anywhere. Set `INFINITE_CANVAS_GENERATOR=diffusers` to use the Stable Diffusion context-frame inpainting path.

## Run

```powershell
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Diffusers Mode

Install GPU dependencies for your CUDA runtime, then run:

```powershell
$env:INFINITE_CANVAS_GENERATOR="diffusers"
$env:INFINITE_CANVAS_INPAINT_MODEL_ID="runwayml/stable-diffusion-inpainting"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

