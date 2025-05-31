import os
import asyncio
from typing import List
from pydub import AudioSegment
from agents import async_groq_client


class TranscriptionService:
    MAX_FILE_SIZE_MB = 5
    CHUNK_DURATION_MS = 300_000  # 5 minutes

    def __init__(self, chunk_dir: str = "chunks"):
        self.chunk_dir = chunk_dir
        self.groq_client = async_groq_client
        os.makedirs(self.chunk_dir, exist_ok=True)

    async def transcribe(self, file_path: str, prompt: str = "") -> str:
        """Transcribes the file directly or in chunks if file size > 5MB."""

        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        print(f"[Info] File size: {file_size_mb:.2f} MB")

        if file_size_mb > self.MAX_FILE_SIZE_MB:
            print("[Info] File exceeds 5MB. Starting chunked transcription.")
            return await self._transcribe_in_chunks(file_path, prompt)

        print("[Info] File under 5MB. Starting direct transcription.")
        return await self._transcribe_single(file_path, prompt)

    async def _transcribe_in_chunks(self, file_path: str, prompt: str = "") -> str:
        audio = AudioSegment.from_file(file_path)
        chunk_paths = self._chunk_audio(audio, file_path)
        print(f"[Chunking] {len(chunk_paths)} chunks created.")

        try:
            tasks = [self._transcribe_single(chunk, prompt) for chunk in chunk_paths]
            results = await asyncio.gather(*tasks)
            return "\n".join(results)
        finally:
            self._cleanup_chunks(chunk_paths)

    async def _transcribe_single(self, file_path: str, prompt: str = "") -> str:
        print(f"[Transcription] Processing: {file_path}")
        with open(file_path, "rb") as audio_file:
            result = await self.groq_client.audio.transcriptions.create(
                file=audio_file,
                model="whisper-large-v3-turbo",
                prompt=prompt,
                response_format="verbose_json",
                timestamp_granularities=["word", "segment"],
                language="en",
                temperature=0.0
            )
        print(f"[Transcription] Done: {file_path}")
        return result.text

    def _chunk_audio(self, audio: AudioSegment, file_path: str) -> List[str]:
        chunks = [audio[i:i + self.CHUNK_DURATION_MS] for i in range(0, len(audio), self.CHUNK_DURATION_MS)]
        base_name = os.path.splitext(os.path.basename(file_path))[0]

        chunk_paths = []
        for idx, chunk in enumerate(chunks):
            chunk_path = os.path.join(self.chunk_dir, f"{base_name}_chunk{idx}.mp3")
            chunk.export(chunk_path, format="mp3")
            print(f"[Chunking] Saved: {chunk_path}")
            chunk_paths.append(chunk_path)

        return chunk_paths

    def _cleanup_chunks(self, chunk_paths: List[str]) -> None:
        for path in chunk_paths:
            try:
                os.remove(path)
                print(f"[Cleanup] Deleted: {path}")
            except Exception as e:
                print(f"[Cleanup] Failed to delete {path}: {e}")
