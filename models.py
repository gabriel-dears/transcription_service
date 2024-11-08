from pydantic import BaseModel


class AudioFile(BaseModel):
    audio_path: str
