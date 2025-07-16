import asyncio
from io import BytesIO
from typing import List
from agents import async_groq_client
import boto3
from pydub import AudioSegment
from settings import Settings

settings = Settings()

class TranscriptionService:
    MAX_CHUNK_SIZE_MB = 5
    
    def __init__(self, bucket_name: str):
        self.groq_client = async_groq_client
        self.s3 = boto3.client(
            "s3",
            aws_access_key_id=settings.aws_access_key,
            aws_secret_access_key=settings.aws_secret_access_key,
            # region_name="us-east-1"  # Adjust region as needed
        )
        self.bucket = bucket_name
    
    async def transcribe(self, filename: str, prompt: str = "") -> str:

        response = self.s3.get_object(Bucket=self.bucket, Key=filename)
        audio_bytes = response["Body"].read()
        
        # Load audio from bytes
        audio = AudioSegment.from_file(BytesIO(audio_bytes))
        
        # Check if chunking is needed
        if len(audio_bytes) <= self.MAX_CHUNK_SIZE_MB * 1024 * 1024:
            print("[Info] File size within limits, processing as single chunk")
            # Create a properly named BytesIO for the whole file
            audio_stream = BytesIO(audio_bytes)
            audio_stream.name = filename  # Set the name attribute
            return await self._transcribe_chunk(audio_stream, prompt)
        
        # File is too large, chunk it
        chunks = self._chunk_audio_to_memory(audio)
        
        tasks = [self._transcribe_chunk(chunk, prompt) for chunk in chunks]
        results = await asyncio.gather(*tasks)
        self.s3.delete_object(Bucket=self.bucket, Key=filename)  # Clean up the original file
        return "\n".join(results)
    
    def _chunk_audio_to_memory(self, audio: AudioSegment) -> List[BytesIO]:
        max_bytes = self.MAX_CHUNK_SIZE_MB * 1024 * 1024
        bytes_per_ms_est = (len(audio.raw_data) / len(audio))  # size per ms
        chunk_duration = int(max_bytes / bytes_per_ms_est)
        
        chunks = [
            audio[i:i + chunk_duration] for i in range(0, len(audio), chunk_duration)
        ]
        
        byte_chunks = []
        for i, chunk in enumerate(chunks):
            buf = BytesIO()
            chunk.export(buf, format="mp3")  # ensure valid format
            buf.seek(0)
            buf.name = f"chunk_{i}.mp3"  # Set the name attribute with proper extension
            byte_chunks.append(buf)
            print(f"[Chunking] Exported chunk {i} to mp3 ({buf.getbuffer().nbytes / (1024 * 1024):.2f} MB)")
        
        return byte_chunks
    
    async def _transcribe_chunk(self, audio_stream: BytesIO, prompt: str) -> str:
        
        # Ensure the stream is at the beginning
        audio_stream.seek(0)
        
        try:
            result = await self.groq_client.audio.transcriptions.create(
                file=audio_stream,
                model="whisper-large-v3-turbo",
                prompt=prompt,
                response_format="verbose_json",
                timestamp_granularities=["word", "segment"],
                language="en",
                temperature=0.0
            )
            return result.text
        except Exception as e:
            print(f"[Error] Transcription failed: {str(e)}")
            # You might want to return empty string or raise depending on your needs
            return ""