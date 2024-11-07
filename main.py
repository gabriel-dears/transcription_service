from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import wave
import json
from vosk import Model, KaldiRecognizer

class AudioFile(BaseModel):
    audio_path: str


app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Transcription Service is running"}


@app.post("/transcribe")
async def transcribe_audio(audio_file: AudioFile):
    model = Model("/home/gabriel/Downloads/vosk-model-small-pt-0.3")  # Adjust to your model's path
    recognizer = KaldiRecognizer(model, 16000)  # Adjust the sample rate if necessary

    with wave.open(audio_file.audio_path, "rb") as wf:
        if wf.getframerate() != 16000:
            raise HTTPException(status_code=400, detail="Audio file must have a 16kHz sample rate")

        results = []
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if recognizer.AcceptWaveform(data):
                results.append(json.loads(recognizer.Result()))

        # After the loop, get the final results
        final_result = json.loads(recognizer.FinalResult())
        results.append(final_result)

    # Combine results and return them as a single string
    transcript = " ".join([result['text'] for result in results])
    return {"transcription": transcript}

