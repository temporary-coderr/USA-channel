import os
from pathlib import Path

import modal
from fastapi import Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

APP_NAME = "usa-channel-voice"
VOICE_PATH = "/root/voice/sndp_reference.mp3"
IMAGE = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .uv_pip_install(
        "chatterbox-tts==0.1.6",
        "fastapi[standard]==0.124.4",
        "peft==0.18.0",
        "soundfile",
    )
    .add_local_file("voice/sndp_reference.mp3", remote_path=VOICE_PATH)
)
app = modal.App(APP_NAME)


class SpeechRequest(BaseModel):
    text: str


@app.cls(
    image=IMAGE,
    gpu="A10G",
    timeout=900,
    scaledown_window=300,
    secrets=[modal.Secret.from_dict({"VOICE_API_TOKEN": os.environ["VOICE_API_TOKEN"]})],
)
@modal.concurrent(max_inputs=1)
class ChatterboxVoice:
    @modal.enter()
    def load(self):
        from chatterbox.tts_turbo import ChatterboxTurboTTS
        self.model = ChatterboxTurboTTS.from_pretrained(device="cuda")

    @modal.fastapi_endpoint(method="POST", docs=False)
    def generate(self, body: SpeechRequest, authorization: str = Header(default="")):
        import io
        import torch
        import torchaudio

        expected = os.environ.get("VOICE_API_TOKEN", "")
        supplied = authorization.removeprefix("Bearer ").strip()
        if not expected or supplied != expected:
            raise HTTPException(status_code=401, detail="Unauthorized")
        text = body.text.strip()
        if not text or len(text) > 12000:
            raise HTTPException(status_code=400, detail="Text must contain 1–12000 characters")
        audio = self.model.generate(text, audio_prompt_path=VOICE_PATH)
        buffer = io.BytesIO()
        torchaudio.save(buffer, audio.detach().cpu(), self.model.sr, format="wav")
        return Response(content=buffer.getvalue(), media_type="audio/wav")
