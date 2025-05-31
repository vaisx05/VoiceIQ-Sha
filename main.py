from transcription import TranscriptionService
from santization import SanitizationService
from agents import deps, call_log_agent, report_agent, database_agent, chat_agent, async_groq_client
from memory import MemoryHandler
from database import DatabaseHandler
from filename_parser import parse_call_filename

from pydantic_ai.messages import SystemPromptPart, ModelRequest
import traceback
from uuid import UUID
import re
from settings import Settings

settings = Settings()

transcription_service = TranscriptionService()
sanitization_service = SanitizationService()
memory = MemoryHandler(deps=deps)
db = DatabaseHandler(deps=deps)

async def create_initial_log(file_path: str) -> str:
    print(f"[CreateInitialLog] Start: {file_path}")
    metadata = await parse_call_filename(filename=file_path)
    print(f"[CreateInitialLog] Parsed metadata: {metadata}")

    payload = {
        "filename": metadata["filename"],
        "call_type": metadata["call_type"],
        "toll_free_did": metadata["toll_free_did"],
        "agent_extension": metadata["agent_extension"],
        "customer_number": metadata["customer_number"],
        "call_date": metadata["call_date"],
        "call_start_time": metadata["call_start_time"],
        "call_id": metadata["call_id"],
        "status": "processing"
    }

    response = await db.create_call_log(data=payload)
    print(f"[CreateInitialLog] DB Response: {response}")
    return response.get("id")

async def complete_log_processing(file_path: str, log_id: UUID):
    print(f"[Transcription] Processing: {file_path}")
    transcript = await transcription_service.transcribe(file_path=file_path)
    print(f"[Transcription] Done: {file_path}")

    print(f"[Sanitization] Start")
    sanitized_transcript = await sanitization_service.sanitize(transcript=transcript)
    print(f"[Sanitization] Done")

    print(f"[CallLogAgent] Running")
    call_log_agent_response = await call_log_agent.run(user_prompt=sanitized_transcript)
    print(f"[CallLogAgent] Done")

    print(f"[ReportAgent] Running")
    report_agent_response = await report_agent.run(user_prompt=sanitized_transcript)
    print(f"[ReportAgent] Done")

    report_cleaned_response = re.sub(r'<think>.*?</think>', '', report_agent_response.output, flags=re.DOTALL)

    print(f"[DatabaseAgent] Running")
    database_agent_response = await database_agent.run(user_prompt=sanitized_transcript)
    print(f"[DatabaseAgent] Done")

    if not database_agent_response.output:
        print("[DatabaseAgent] Failed to extract structured data")
        raise ValueError("Database Agent failed to extract structured data")

    update_payload = {
        "responder_name": database_agent_response.output.responder_name,
        "caller_name": database_agent_response.output.caller_name,
        "request_type": database_agent_response.output.request_type,
        "issue_summary": database_agent_response.output.issue_summary,
        "caller_sentiment": database_agent_response.output.caller_sentiment,
        "report_generated": report_cleaned_response,
        "call_log": call_log_agent_response.output,
        "transcription": sanitized_transcript,
        "status": "complete"
    }

    print(f"[DB] Updating log {log_id} with processed data")
    await db.update_call_log(log_id, update_payload)
    print(f"[DB] Update complete for log {log_id}")

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
