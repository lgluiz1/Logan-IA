# Whisper STT Server

"""
Servidor FastAPI para transcrição de áudio usando faster-whisper.
Expõe endpoint simples para o Logan AI.
"""

import io
import os
import tempfile

from fastapi import FastAPI, File, UploadFile
from faster_whisper import WhisperModel

app = FastAPI(title="Logan AI — Whisper STT")

# Configuração
MODEL_SIZE = os.getenv("WHISPER_MODEL", "small")
LANGUAGE = os.getenv("WHISPER_LANGUAGE", "pt")
DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

# Carrega modelo na inicialização
model = WhisperModel(
    MODEL_SIZE,
    device=DEVICE,
    compute_type=COMPUTE_TYPE,
)


@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """Transcreve áudio para texto.

    Aceita arquivos WAV, MP3, FLAC ou raw PCM.
    """
    # Salva arquivo temporário
    content = await audio.read()

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
        tmp.write(content)
        tmp.flush()

        # Transcreve
        segments, info = model.transcribe(
            tmp.name,
            language=LANGUAGE,
            vad_filter=True,
            beam_size=5,
            initial_prompt="Logan, qual a temperatura, combustível, erro, injeção, motor.",
        )

        # Combina segmentos
        text = " ".join(segment.text.strip() for segment in segments)

    return {
        "text": text,
        "language": info.language,
        "language_probability": info.language_probability,
        "duration": info.duration,
    }


@app.get("/health")
async def health():
    return {"status": "ok", "model": MODEL_SIZE}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)
