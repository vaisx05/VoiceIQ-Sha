from database import DatabaseHandler
from transcription import TranscriptionService
from agents import deps, call_log_agent, report_agent, database_agent
import traceback
from settings import Settings

settings = Settings()

db = DatabaseHandler(deps)

transcription_service = TranscriptionService()

async def main(file_path: str) -> None:
    try:
        transcript = await transcription_service.transcribe_local(file_path=file_path)
        sanitized_transcript = await transcription_service.filter(transcript=transcript)
        print("✅ Transcription successful.")
        
        call_log_agent_response = await call_log_agent.run(user_prompt=sanitized_transcript)
        report_agent_response = await report_agent.run(user_prompt=sanitized_transcript)
        database_agent_response = await database_agent.run(user_prompt=sanitized_transcript)
        if not database_agent_response.data:
            raise ValueError("Database Agent failed to extract structured data")
        print("✅ Agents executed successfully.")
        
        payload : dict = {
            "responder_name": database_agent_response.data.responder_name,
            "caller_name": database_agent_response.data.caller_name,
            "request_type": database_agent_response.data.request_type,
            "issue_summary": database_agent_response.data.issue_summary,
            "caller_sentiment": database_agent_response.data.caller_sentiment,
            "report_generated": report_agent_response.data,
            "call_log": call_log_agent_response.data
        }
        print("✅ Payload created successfully.")
        
        await db.create_call_log(data=payload)
        print("✅ Log inserted successfully.")

    except Exception as e:
        print(traceback.format_exc())
