import os
from fastapi import HTTPException


def check_file_exists(file_path: str):
    """Check if the audio file exists."""
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Audio file not found")
