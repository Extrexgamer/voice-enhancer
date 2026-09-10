from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

import os
import uuid
import subprocess


app = FastAPI(
    title="VoxEnhance AI API",
    version="0.2.0"
)

# Allow GitHub Pages frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "name": "VoxEnhance AI API",
        "status": "online",
        "health": "/health",
        "docs": "/docs"
    }


@app.get("/health")
def health():
    return {"ok": True}


def cleanup_file(path: str):
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


@app.post("/enhance")
async def enhance(
    file: UploadFile = File(...),
    noise_reduction: int = Form(60),
    clarity: int = Form(70),
    warmth: int = Form(35),
    gain: int = Form(100),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Audio file required")

    # Don't rely only on browser MIME type.
    # Browsers can report M4A as application/octet-stream.
    filename = file.filename.lower()

    allowed_extensions = (
        ".mp3",
        ".wav",
        ".m4a",
        ".aac",
        ".ogg",
        ".oga",
        ".webm",
        ".flac",
        ".mp4"
    )

    if not filename.endswith(allowed_extensions):
        raise HTTPException(
            status_code=400,
            detail="Unsupported audio format"
        )

    # Clamp values
    nr = max(0, min(100, noise_reduction))
    cl = max(0, min(100, clarity))
    wa = max(0, min(100, warmth))
    gn = max(50, min(150, gain))

    input_path = f"/tmp/{uuid.uuid4().hex}_{filename}"
    output_path = f"/tmp/{uuid.uuid4().hex}_enhanced.wav"

    try:
        # Save uploaded file
        with open(input_path, "wb") as f:
            content = await file.read()

            if not content:
                raise HTTPException(
                    status_code=400,
                    detail="Empty audio file"
                )

            # 50 MB safety limit
            if len(content) > 50 * 1024 * 1024:
                raise HTTPException(
                    status_code=413,
                    detail="Audio file is too large. Maximum 50 MB."
                )

            f.write(content)

        # -----------------------------------------
        # Enhancement parameters
        # -----------------------------------------

        # Noise reduction:
        # 0   -> almost none
        # 100 -> stronger denoise
        denoise_db = 6 + (nr * 0.20)

        # Clarity:
        # Presence boost around speech frequencies
        presence_gain = 0.5 + (cl * 0.025)

        # Warmth:
        # Low-mid boost
        warmth_gain = (wa * 0.035)

        # Output gain
        output_volume = gn / 100.0

        # High-pass removes low rumble.
        highpass_freq = 60 + int(nr * 0.5)

        # -----------------------------------------
        # FFmpeg processing chain
        # -----------------------------------------

        filters = (
            f"highpass=f={highpass_freq},"
            f"afftdn=nr={denoise_db:.1f}:nf=-50,"
            f"equalizer=f=180:t=q:w=0.8:g={warmth_gain:.2f},"
            f"equalizer=f=3200:t=q:w=1.0:g={presence_gain:.2f},"
            f"equalizer=f=5500:t=q:w=0.8:g={presence_gain * 0.45:.2f},"
            "acompressor="
            "threshold=-20dB:"
            "ratio=3:"
            "attack=10:"
            "release=120:"
            "makeup=2,"
            f"volume={output_volume:.2f},"
            "loudnorm=I=-16:TP=-1.5:LRA=11"
        )

        command = [
            "ffmpeg",
            "-y",
            "-i",
            input_path,
            "-vn",
            "-af",
            filters,
            "-ar",
            "48000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            output_path,
        ]

        process = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        if process.returncode != 0:
            print("FFmpeg ERROR:")
            print(process.stderr)

            raise HTTPException(
                status_code=500,
                detail="FFmpeg processing failed"
            )

        if not os.path.exists(output_path):
            raise HTTPException(
                status_code=500,
                detail="Enhanced audio was not created"
            )

        # Delete both temporary files after response is sent
        background_task = BackgroundTask(
            lambda: (
                cleanup_file(input_path),
                cleanup_file(output_path)
            )
        )

        return FileResponse(
            output_path,
            media_type="audio/wav",
            filename="enhanced-voice.wav",
            background=background_task
        )

    except HTTPException:
        cleanup_file(input_path)
        cleanup_file(output_path)
        raise

    except Exception as e:
        print("SERVER ERROR:", repr(e))

        cleanup_file(input_path)
        cleanup_file(output_path)

        raise HTTPException(
            status_code=500,
            detail="Audio processing failed"
    )
