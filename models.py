from typing import List

from pydantic import BaseModel


class AudioFile(BaseModel):
    audio_path: str


class AudioChunkMessage(BaseModel):
    channelId: str
    videoId: str
    audioChunk: str
    tags: List[str] = []
    category: str
    audioPart: str
