import speech_recognition as sr
from fastapi import HTTPException
from typing import Union, IO


def load_audio(audio: Union[str, IO[bytes]]):
    """
    Load the audio file (either a file path or file-like object) and prepare for transcription.

    :param audio: Path to the audio file or a file-like object (e.g., BytesIO).
    :return: Recognizer audio object ready for transcription.
    """
    recognizer = sr.Recognizer()

    try:
        # Determine whether the input is a file path or file-like object
        if isinstance(audio, str):
            audio_source = sr.AudioFile(audio)
        elif hasattr(audio, "read"):
            audio_source = sr.AudioFile(audio)
        else:
            raise HTTPException(status_code=400, detail="Invalid audio input. Must be a file path or file-like object.")

        # Load and process audio
        with audio_source as source:
            recognizer.adjust_for_ambient_noise(source)
            return recognizer.record(source)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading audio: {str(e)}")


def transcribe_audio_file(audio):
    """
    Transcribe the audio data using Google Speech Recognition.

    :param audio: Recognizer audio object loaded via `load_audio`.
    :return: Transcribed text as a string.
    """
    recognizer = sr.Recognizer()

    try:
        transcript = recognizer.recognize_google(audio, language="pt-BR")
        return transcript
    except sr.UnknownValueError:
        raise HTTPException(status_code=400, detail="Google Speech Recognition could not understand the audio")
    except sr.RequestError:
        raise HTTPException(status_code=500, detail="Could not request results from Google Speech Recognition service")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error during transcription: {str(e)}")
