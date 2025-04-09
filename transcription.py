import os
import mimetypes
import requests
import re
from groq import Groq
from settings import Settings

settings = Settings()

class TranscriptionService:
    def __init__(self):
        self.groq_client = Groq(api_key=settings.groq_api_key)
        self.remote_url = "https://guest1.nullvijayawada.org/transcribe"

    def _load_audio_file(self, file_path: str) -> tuple[str, bytes, str]:
        """Returns filename, file bytes, and MIME type."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File '{file_path}' does not exist.")

        mime_type, _ = mimetypes.guess_type(file_path)
        mime_type = mime_type or 'application/octet-stream'

        with open(file_path, 'rb') as f:
            file_bytes = f.read()

        return os.path.basename(file_path), file_bytes, mime_type

    def transcribe_local(self, file_path: str) -> str:
        """Uses external transcription API via HTTP POST."""
        filename, file_bytes, mime_type = self._load_audio_file(file_path)
        files = {'file': (filename, file_bytes, mime_type)}
        response = requests.post(self.remote_url, files=files)

        if response.ok:
            return response.text
        else:
            raise RuntimeError(f"Transcription failed: {response.status_code} - {response.text}")

    def transcribe_groq(self, file_path: str, prompt: str = "Specify context or spelling") -> str:
        """Uses Groq's Whisper API to transcribe audio."""
        _, file_bytes, _ = self._load_audio_file(file_path)

        with open(file_path, "rb") as f:
            transcription = self.groq_client.audio.transcriptions.create(
                file=f,
                model="whisper-large-v3-turbo",
                prompt=prompt,
                response_format="verbose_json",
                timestamp_granularities=["word", "segment"],
                language="en",
                temperature=0.0
            )
        return transcription.text

    def filter(self, transcript: str) -> str:
        """Sanitize PII like card numbers and SSNs."""
        # Mask card numbers
        card_pattern = r'\b((?:\d[ -]?){6})(?:(?:[Xx\- ]{1,6}|\d[ -]?){2,9})([ -]?\d{4})\b'
        def mask_card(match):
            first = re.sub(r'\D', '', match.group(1))[:6]
            last = re.sub(r'\D', '', match.group(2))[-4:]
            masked = f"{first}{'X' * max(0, 16 - len(first) - len(last))}{last}"
            return masked

        sanitized = re.sub(card_pattern, mask_card, transcript)

        # Mask SSNs
        ssn_pattern = r'\b(\d{3}|X{3})[- ]?(\d{2}|X{2})[- ]?(\d{4})\b'
        sanitized = re.sub(ssn_pattern, r'XXX-XX-\3', sanitized)

        return sanitized
