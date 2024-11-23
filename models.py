from pydantic import BaseModel


class AudioFile(BaseModel):
    audio_path: str


class AudioChunkMessage(BaseModel):
    channelId: str
    videoId: str
    audioChunk: str
