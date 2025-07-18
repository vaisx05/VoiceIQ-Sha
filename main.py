from transcription import TranscriptionService
from santization import SanitizationService
from agents import deps, call_log_agent, report_agent, database_agent, chat_agent, questionary_agent
from memory import MemoryHandler
from database import DatabaseHandler
from filename_parser import parse_call_filename
import transcription
from upload_filename_parser import upload_parse_call_filename

from pydantic_ai.messages import SystemPromptPart, ModelRequest
from uuid import UUID
import re
from settings import Settings
import logfire
import json

settings = Settings()
logfire.configure(token=settings.logfire_write_token)
transcription_service = TranscriptionService(bucket_name="call-logs-audio-files")
sanitization_service = SanitizationService()
memory = MemoryHandler(deps=deps)
db = DatabaseHandler(deps=deps)

@logfire.instrument("process_log")
async def process_log(filename: str, log_id: str) -> str:

    metadata = await parse_call_filename(filename=filename)

    transcript = await transcription_service.transcribe(filename=filename, prompt="Transcribe and pay close attention to smaller details like names and personal details")

    sanitized_transcript = await sanitization_service.sanitize(transcript=transcript)

    call_log_agent_response = await call_log_agent.run(user_prompt=sanitized_transcript)

    report_agent_response = await report_agent.run(user_prompt=sanitized_transcript)

    report_cleaned_response = re.sub(r'<think>.*?</think>', '', report_agent_response.output, flags=re.DOTALL)

    database_agent_response = await database_agent.run(user_prompt=sanitized_transcript)

    if not database_agent_response.output:
        raise ValueError("Database Agent failed to extract structured data")
    
    common_questions = await db.get_common_questions(organisation_id)

    questions = [q["question_text"] for q in common_questions]

    combined_prompt = f"""Transcript Context:
                      {sanitized_transcript}

                         Questions to Answer:
                    {'\n'.join(questions)}
   """
    question_answer_response = await questionary_agent.run(user_prompt=combined_prompt)

    answers_data = json.loads(question_answer_response.output)
    for item in answers_data["answers"]:
        matching_question = next(
            (q for q in common_questions if q["question_text"] == item["question_text"]),
            None
        )
        if not matching_question:
            continue
        
        answer_payload = {
            "call_id": log_id,
            "question_id": matching_question["id"],
            "answer_text": item["answer_text"]
        }
        await db.create_answer(answer_payload)

    payload = {
        "responder_name": database_agent_response.output.responder_name,
        "caller_name": database_agent_response.output.caller_name,
        "request_type": database_agent_response.output.request_type,
        "issue_summary": database_agent_response.output.issue_summary,
        "key_points": database_agent_response.output.key_points,
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

@logfire.instrument("upload_process_log")
async def upload_process_log(
    filename: str,
    log_id: str,
    organisation_id: str,
    db
) -> str:
    metadata = await upload_parse_call_filename(filename=filename)

    transcript = await transcription_service.transcribe(
        filename=filename,
        prompt="Transcribe and pay close attention to smaller details like names and personal details"
    )

    sanitized_transcript = await sanitization_service.sanitize(transcript=transcript)

    call_log_agent_response = await call_log_agent.run(user_prompt=sanitized_transcript)
    report_agent_response = await report_agent.run(user_prompt=sanitized_transcript)
    report_cleaned_response = re.sub(r'<think>.*?</think>', '', report_agent_response.output, flags=re.DOTALL)
    database_agent_response = await database_agent.run(user_prompt=sanitized_transcript)

    if not database_agent_response.output:
        raise ValueError("Database Agent failed to extract structured data")
    
    common_questions = await db.get_common_questions(organisation_id)
    questions = [q["question_text"] for q in common_questions]

    combined_prompt = f"""Transcript Context:
                      {sanitized_transcript}

                         Questions to Answer:
                    {'\n'.join(questions)}
   """
    question_answer_response = await questionary_agent.run(user_prompt=combined_prompt)

    # for item in question_answer_response.output.answers:
    #     matching_question = next(
    #         (q for q in common_questions if q["question_text"] == item.question_text),
    #         None
    #     )
    #     if not matching_question:
    #         continue
    #     print(f"Call id:{log_id}")
    #     answer_payload = {
    #         "call_id": log_id,
    #         "question_id": matching_question["id"],
    #         "answer_text": item.answer_text
    #     }
    #     await db.create_answer(answer_payload)

    try:
        output = question_answer_response.output.strip()
        output = re.sub(r"^```(?:json)?|```$", "", output, flags=re.MULTILINE).strip()
        answers_data = json.loads(output)
        answers = answers_data["answers"]
    except Exception as e:
        print("Failed to parse answers:", question_answer_response.output)
        answers = []

    for item in answers:
        matching_question = next(
            (q for q in common_questions if q["question_text"] == item["question_text"]),
            None
        )
        if not matching_question:
            continue
        print(f"Call id:{log_id}")
        answer_payload = {
            "call_id": log_id,
            "question_id": matching_question["id"],
            "answer_text": item["answer_text"]
        }
        await db.create_answer(answer_payload)

    payload = {
        "responder_name": getattr(database_agent_response.output, "responder_name", None),
        "caller_name": getattr(database_agent_response.output, "caller_name", None),
        "request_type": getattr(database_agent_response.output, "request_type", None),
        "issue_summary": getattr(database_agent_response.output, "issue_summary", None),
        "key_points": getattr(database_agent_response.output, "key_points", None),
        "caller_sentiment": getattr(database_agent_response.output, "caller_sentiment", None),
        "report_generated": report_cleaned_response,
        "call_log": getattr(call_log_agent_response, "output", None),
        "transcription": sanitized_transcript,
        "filename": metadata.get("filename"),
        "call_type": metadata.get("call_type"),
        "toll_free_did": metadata.get("toll_free_did"),
        "agent_extension": metadata.get("agent_extension"),
        "customer_number": metadata.get("customer_number"),
        "call_date": metadata.get("call_date"),
        "call_start_time": metadata.get("call_start_time"),
        "call_id": metadata.get("call_id"),
    }
    
    return payload
@logfire.instrument("chat")
async def chat(user_prompt: str, uuid : UUID, organisation_id: str) -> str:
    print(f"[Chat] User prompt: {user_prompt} | Log UUID: {uuid}")

    user_id : str = "TestUser"
    messages = await memory.get_memory(user_id=user_id, organisation_id=organisation_id, limit=20)
    print(f"[Chat] Retrieved {len(messages)} messages from memory")

    await memory.append_message(user_id=user_id, organisation_id=organisation_id, role="user", content=user_prompt)
    print(f"[Chat] Appended user message")

    # transcription = await db.get_transcription(uuid=uuid)
    # print(f"[Chat] Retrieved transcription from DB")

    transcription = await db.get_transcription(uuid=uuid)
    if not transcription or "transcription" not in transcription:
        raise ValueError("No transcription found for this call log")

    messages.append(ModelRequest(parts=[SystemPromptPart(content=transcription["transcription"])]))

    response = await chat_agent.run(user_prompt=user_prompt, message_history=messages)
    bot_response = response.output

    print(f"[Chat] Agent response: {bot_response}")

    await memory.append_message(user_id=user_id, organisation_id=organisation_id, role="bot", content=bot_response)
    print(f"[Chat] Appended bot response")

    return bot_response
