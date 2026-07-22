# Kokoro TTS Server

"""
Servidor FastAPI para síntese de voz usando Kokoro TTS.
Expõe API compatível com OpenAI speech endpoint.
"""

import io
import os

import numpy as np
from fastapi import FastAPI
from fastapi.responses import Response
from pydantic import BaseModel

app = FastAPI(title="Logan AI — Kokoro TTS")

# Configuração
DEFAULT_VOICE = os.getenv("KOKORO_VOICE", "pf_dora")

# Inicializa pipeline
pipeline = None


def get_pipeline():
    global pipeline
    if pipeline is None:
        try:
            from pykokoro import KokoroPipeline, PipelineConfig
            config = PipelineConfig(voice=DEFAULT_VOICE)
            pipeline = KokoroPipeline(config)
        except ImportError:
            from kokoro import KPipeline
            # O código da língua no Kokoro geralmente é a primeira letra da voz 
            # (p = Portuguese, a = American English, etc)
            lang_code = DEFAULT_VOICE[0] if DEFAULT_VOICE else "p"
            pipeline = KPipeline(lang_code=lang_code)
    return pipeline


class SpeechRequest(BaseModel):
    model: str = "kokoro"
    input: str
    voice: str = DEFAULT_VOICE
    speed: float = 1.0
    response_format: str = "pcm"  # pcm, wav, mp3


@app.post("/v1/audio/speech")
async def synthesize(request: SpeechRequest):
    """Sintetiza texto em áudio.

    Compatível com a API OpenAI /v1/audio/speech.
    """
    pipe = get_pipeline()

    # Gera áudio
    audio = pipe(request.input, voice=request.voice, speed=request.speed)

    # KPipeline do kokoro retorna um gerador que gera objetos Result
    # KokoroPipeline do pykokoro (se existir) pode retornar uma tupla (audio_data, sample_rate)
    if isinstance(audio, tuple):
        audio_data, sample_rate = audio
    elif hasattr(audio, "__iter__") or hasattr(audio, "__next__"):
        audio_data_list = []
        for r in audio:
            val = None
            if hasattr(r, "audio"):
                val = r.audio
            elif isinstance(r, tuple) and len(r) >= 3:
                val = r[2]
            else:
                val = r

            if val is not None:
                if hasattr(val, "cpu"):
                    val = val.cpu()
                if hasattr(val, "numpy"):
                    val = val.numpy()
                audio_data_list.append(val)
        
        if audio_data_list:
            if isinstance(audio_data_list[0], np.ndarray):
                audio_data = np.concatenate(audio_data_list)
            else:
                audio_data = b"".join(audio_data_list)
        else:
            audio_data = np.array([], dtype=np.float32)
        sample_rate = 24000
    else:
        audio_data = audio
        sample_rate = 24000

    # Converte para formato solicitado
    if isinstance(audio_data, np.ndarray):
        # Normaliza para int16
        if audio_data.dtype == np.float32 or audio_data.dtype == np.float64:
            audio_int16 = (audio_data * 32767).astype(np.int16)
        else:
            audio_int16 = audio_data.astype(np.int16)
        pcm_bytes = audio_int16.tobytes()
    else:
        pcm_bytes = bytes(audio_data)

    if request.response_format == "pcm":
        return Response(
            content=pcm_bytes,
            media_type="audio/pcm",
        )
    elif request.response_format == "wav":
        import soundfile as sf
        buffer = io.BytesIO()
        sf.write(
            buffer,
            np.frombuffer(pcm_bytes, dtype=np.int16),
            sample_rate,
            format="WAV",
        )
        buffer.seek(0)
        return Response(
            content=buffer.read(),
            media_type="audio/wav",
        )
    else:
        return Response(
            content=pcm_bytes,
            media_type="audio/pcm",
        )


@app.get("/health")
async def health():
    return {"status": "ok", "voice": DEFAULT_VOICE}


@app.on_event("startup")
def startup_event():
    """Preload the Kokoro pipeline on server startup."""
    get_pipeline()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8880)
