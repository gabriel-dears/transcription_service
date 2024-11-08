import speech_recognition as sr
from fastapi import HTTPException


def load_audio(audio_path: str):
    """Load the audio file and prepare for transcription."""
    recognizer = sr.Recognizer()

    try:
        with sr.AudioFile(audio_path) as source:
            recognizer.adjust_for_ambient_noise(source)
            return recognizer.record(source)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading audio: {str(e)}")


def transcribe_audio_file(audio):
    """Transcribe the audio file using Google Speech Recognition."""
    recognizer = sr.Recognizer()

    try:
        transcript = recognizer.recognize_google(audio, language="pt-BR")
        return transcript
    except sr.UnknownValueError:
        raise HTTPException(status_code=400, detail="Google Speech Recognition could not understand the audio")
    except sr.RequestError:
        raise HTTPException(status_code=500, detail="Could not request results from Google Speech Recognition service")
