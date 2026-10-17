"""Application Configuration Module."""

import os
from pydantic import BaseModel, Field


class Settings(BaseModel):
    OLLAMA_HOST: str = Field(default_factory=lambda: os.getenv("OLLAMA_HOST", "http://localhost:11434"))
    MODEL_NAME: str = Field(default_factory=lambda: os.getenv("MODEL_NAME", "gemma2:2b"))
    MAX_CONTEXT_CHARS: int = Field(default_factory=lambda: int(os.getenv("MAX_CONTEXT_CHARS", "12000")))
    MIN_TEXT_CHARS_THRESHOLD: int = Field(default_factory=lambda: int(os.getenv("MIN_TEXT_CHARS_THRESHOLD", "30")))
    MAX_FILE_SIZE_BYTES: int = Field(default_factory=lambda: int(os.getenv("MAX_FILE_SIZE_BYTES", str(25 * 1024 * 1024))))


settings = Settings()
