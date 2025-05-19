from transcription import TranscriptionService
from agents import deps, call_log_agent, report_agent, database_agent, chat_agent
from memory import MemoryHandler
from database import DatabaseHandler

from pydantic_ai.messages import SystemPromptPart, ModelRequest
import traceback
from uuid import UUID
from settings import Settings

settings = Settings()

transcription_service = TranscriptionService()

memory = MemoryHandler(deps)

db = DatabaseHandler(deps)

async def main(file_path: str) -> str:
    try:
        transcript = await transcription_service.transcribe_groq(file_path=file_path)
        sanitized_transcript = await transcription_service.filter(transcript=transcript)
        print("✅ Transcription successful.")
        
        call_log_agent_response = await call_log_agent.run(user_prompt=sanitized_transcript)
        report_agent_response = await report_agent.run(user_prompt=sanitized_transcript)
        database_agent_response = await database_agent.run(user_prompt=sanitized_transcript)
        if not database_agent_response.output:
            raise ValueError("Database Agent failed to extract structured data")
        print("✅ Agents executed successfully.")
        
        payload : dict = {
            "responder_name": database_agent_response.output.responder_name,
            "caller_name": database_agent_response.output.caller_name,
            "request_type": database_agent_response.output.request_type,
            "issue_summary": database_agent_response.output.issue_summary,
            "caller_sentiment": database_agent_response.output.caller_sentiment,
            "report_generated": report_agent_response.output,
            "call_log": call_log_agent_response.output,
            "transcription": sanitized_transcript
        }
        print("✅ Payload created successfully.")
        
        response = await db.create_call_log(data=payload)
        id = response.get("id")
        print("✅ Log inserted successfully.")

        return id
    
    except Exception as e:
        print(traceback.format_exc())


async def chat(user_prompt: str, uuid : UUID) -> str:

    user_id : str = "TestUser"

    messages = await memory.get_memory(user_id=user_id, limit=20)

    await memory.append_message(user_id=user_id, role="user", content=user_prompt)
    
    report = await db.get_report(uuid=uuid)
    messages.append(ModelRequest(parts=[SystemPromptPart(content=report[0]["report_generated"])]))
    
    response = await chat_agent.run(user_prompt=user_prompt, message_history=messages)
    bot_response = response.output
    
    await memory.append_message(user_id=user_id, role="bot", content=bot_response)

    return bot_response
