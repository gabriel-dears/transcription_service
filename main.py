from fastapi import FastAPI, HTTPException
from models import AudioFile
from transcription import load_audio, transcribe_audio_file
from utils import check_file_exists


app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Google Speech-to-Text Service is running"}


@app.post("/transcribe")
async def transcribe_audio(audio_file: AudioFile):
    try:
        check_file_exists(audio_file.audio_path)
        audio = load_audio(audio_file.audio_path)
        transcript = transcribe_audio_file(audio)
        return {"transcription": transcript}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")
