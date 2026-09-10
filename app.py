from fastapi import FastAPI,UploadFile,File,Form,HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import subprocess,tempfile,os,uuid
app=FastAPI(title="VoxEnhance AI API")
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_methods=["*"],allow_headers=["*"])
@app.get("/health")
def health(): return {"ok":True}
@app.post("/enhance")
async def enhance(file:UploadFile=File(...),noise_reduction:int=Form(60),clarity:int=Form(70),warmth:int=Form(35),gain:int=Form(100)):
    if not file.content_type or not file.content_type.startswith("audio/"): raise HTTPException(400,"Audio file required")
    src=f"/tmp/{uuid.uuid4().hex}";out=f"/tmp/{uuid.uuid4().hex}.wav"
    try:
        with open(src,"wb") as f:f.write(await file.read())
        nr=max(0,min(100,noise_reduction));cl=max(0,min(100,clarity));wa=max(0,min(100,warmth));gn=max(50,min(150,gain))
        hp=70+int(nr*.7);presence=1+cl/55;low=-1.5+wa/45;vol=gn/100
        filt=f"highpass=f={hp},bass=g={low}:f=180,treble=g={presence}:f=3500,acompressor=threshold=-18dB:ratio=3:attack=15:release=120:makeup=2,volume={vol},loudnorm=I=-16:TP=-1.5:LRA=11"
        p=subprocess.run(["ffmpeg","-y","-i",src,"-af",filt,"-ar","48000","-ac","1",out],capture_output=True)
        if p.returncode: raise HTTPException(500,"FFmpeg processing failed")
        return FileResponse(out,media_type="audio/wav",filename="enhanced-voice.wav")
    finally:
        if os.path.exists(src):os.remove(src)
