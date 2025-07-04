from transcription import TranscriptionService
from santization import SanitizationService
from agents import deps, call_log_agent, report_agent, database_agent, chat_agent
from memory import MemoryHandler
from database import DatabaseHandler
from filename_parser import parse_call_filename

from pydantic_ai.messages import SystemPromptPart, ModelRequest
from uuid import UUID
import re
from settings import Settings
import logfire

settings = Settings()
logfire.configure(token=settings.logfire_write_token)
transcription_service = TranscriptionService(bucket_name="call-logs-audio-files")
sanitization_service = SanitizationService()
memory = MemoryHandler(deps=deps)
db = DatabaseHandler(deps=deps)

@logfire.instrument("process_log")
async def process_log(filename: str) -> str:

    metadata = await parse_call_filename(filename=filename)

    transcript = await transcription_service.transcribe(filename=filename, prompt="Transcribe and pay close attention to smaller details like names and personal details")

    sanitized_transcript = await sanitization_service.sanitize(transcript=transcript)

    call_log_agent_response = await call_log_agent.run(user_prompt=sanitized_transcript)

    report_agent_response = await report_agent.run(user_prompt=sanitized_transcript)

    report_cleaned_response = re.sub(r'<think>.*?</think>', '', report_agent_response.output, flags=re.DOTALL)

    database_agent_response = await database_agent.run(user_prompt=sanitized_transcript)

    if not database_agent_response.output:
        raise ValueError("Database Agent failed to extract structured data")

    payload = {
        "responder_name": database_agent_response.output.responder_name,
        "caller_name": database_agent_response.output.caller_name,
        "request_type": database_agent_response.output.request_type,
        "issue_summary": database_agent_response.output.issue_summary,
        "caller_sentiment": database_agent_response.output.caller_sentiment,
        "report_generated": report_cleaned_response,
        "call_log": call_log_agent_response.output,
        "transcription": sanitized_transcript,
        "filename": metadata["filename"],
        "call_type": metadata["call_type"],
        "toll_free_did": metadata["toll_free_did"],
        "agent_extension": metadata["agent_extension"],
        "customer_number": metadata["customer_number"],
        "call_date": metadata["call_date"],
        "call_start_time": metadata["call_start_time"],
        "call_id": metadata["call_id"]
    }
    
    return payload

@logfire.instrument("chat")
async def chat(user_prompt: str, uuid : UUID) -> str:
    print(f"[Chat] User prompt: {user_prompt} | Log UUID: {uuid}")

    user_id : str = "TestUser"
    messages = await memory.get_memory(user_id=user_id, limit=20)
    print(f"[Chat] Retrieved {len(messages)} messages from memory")

    await memory.append_message(user_id=user_id, role="user", content=user_prompt)
    print(f"[Chat] Appended user message")

    transcription = await db.get_transcription(uuid=uuid)
    print(f"[Chat] Retrieved transcription from DB")

    messages.append(ModelRequest(parts=[SystemPromptPart(content=transcription["transcription"])]))

    response = await chat_agent.run(user_prompt=user_prompt, message_history=messages)
    bot_response = response.output

    print(f"[Chat] Agent response: {bot_response}")

    await memory.append_message(user_id=user_id, role="bot", content=bot_response)
    print(f"[Chat] Appended bot response")

    return bot_response
