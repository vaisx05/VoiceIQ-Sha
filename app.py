import bcrypt
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import JSONResponse
from filename_parser import parse_call_filename
from pydantic import BaseModel
from typing import List
from agents import deps
from auth import create_access_token, verify_password
from database import DatabaseHandler
from fastapi.middleware.cors import CORSMiddleware
from main import chat, process_log
import traceback
import shutil
import asyncio
from uuid import UUID
import os
from datetime import datetime
import boto3
from transcription import TranscriptionService
import logfire
from settings import Settings

settings = Settings()

s3 = boto3.client(
    "s3",
    aws_access_key_id=settings.aws_access_key,
    aws_secret_access_key=settings.aws_secret_access_key,
    # region_name="us-east-1"  # Adjust region as needed
)

BUCKET_NAME = "call-logs-audio-files" 

db = DatabaseHandler(deps)

transcription_service = TranscriptionService(bucket_name=BUCKET_NAME)

app = FastAPI()

logfire.configure(token=settings.logfire_write_token)
logfire.instrument_fastapi(app=app)

origins = [
    "http://localhost:3000",  
    "http://127.0.0.1:3000",
    "https://voiceiqindominuslabs.vercel.app"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ColumnRequest(BaseModel):
    columns: List[str] | str
    limit: int

class ReportRequest(BaseModel):
    uuid: UUID
    
class ChatRequest(BaseModel):
    user_prompt: str
    uuid: UUID

class Dates(BaseModel):
    from_date: datetime
    to_date: datetime

class VoiceChatRequest(BaseModel):
    file: UploadFile = File(...)
    uuid: UUID

@app.post("/logs/date")
async def get_all_by_dates(req: Dates):
    try:
        call_logs = await db.get_all_by_dates(req.from_date, req.to_date)
        return {"data": call_logs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# @app.get("/logs/all")
# async def get_all_logs():
#     try:
#         result = await db.get_all_logs()
#         return {"data": result}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

@app.get("/logs/all")
async def get_all_logs(limit: int = Query(20, gt=0), offset: int = Query(0, ge=0)):
    try:
        result = await db.get_logs_paginated(limit=limit, offset=offset)
        return {"data": result, "limit": limit, "offset": offset}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/logs/{id}")
async def get_all_by_id(id: str):  # or `id: str` depending on your data type
    try:
        result = await db.get_log(id=id)
        return {"data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/logs/columns")
async def get_columns(req: ColumnRequest):
    try:
        result = await db.get_columns(req.columns, req.limit)
        return {"data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/logs/report")
async def get_report(req: ReportRequest):
    try:
        result = await db.get_report(req.uuid)
        return {"data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/create_log")
async def create_log(file: UploadFile = File(...)):
    allowed_exts = (".wav", ".mp3")
    ext = os.path.splitext(file.filename)[-1].lower()

    if ext not in allowed_exts:
        raise HTTPException(status_code=400, detail="Only .wav or .mp3 files are supported")

    if await db.file_exists(file.filename):
        raise HTTPException(status_code=409, detail="File with this name already uploaded")
    
    # Parse metadata from filename
    metadata = await parse_call_filename(file.filename)
    
    # Insert initial row in Supabase with metadata and status
    initial_payload = {
        **metadata,
        "status": "processing",
    }   

    initial_row = await db.create_call_log(initial_payload)
    log_id = initial_row["id"] 
    
    try:
        file_data = await file.read()

        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=file.filename,
            Body=file_data,
            ContentType=file.content_type
        )

    # except Exception as e:
    #     #If S3 upload fails, update status to "failed"
    #     await db.update_call_log(log_id, {"status": "failed"})
    #     print(traceback.format_exc())
    #     raise HTTPException(status_code=500, detail="S3 upload failed")

        #Start processing in the background
        asyncio.create_task(process_and_update_log(file.filename, log_id))

        return JSONResponse(content={
            "status": "success",
            "message": "Log uploaded and processing complete",
            "uuid": log_id
        })

    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Internal server error")

# Add this function to handle background processing and update
async def process_and_update_log(filename: str, log_id: str):
    from main import process_log
    payload = await process_log(filename)
    update_data = {**payload, "status": "complete"}
    await db.update_call_log(log_id, update_data)

@app.post("/chat")
async def report_chat(ctx : ChatRequest):
    try:
        response = await chat(user_prompt=ctx.user_prompt, uuid=ctx.uuid)
        
        return JSONResponse(content={
            "status": "success",
            "content": response
        })
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/voice_chat")
async def report_voice_chat(file: UploadFile = File(...), uuid: UUID = Form(...)):
    try:
        temp_filename = file.filename

        with open(temp_filename, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        transcript = await transcription_service.transcribe(file_path=temp_filename)

        response = await chat(user_prompt=transcript, uuid=uuid)
        
        if os.path.exists(temp_filename):
            os.remove(temp_filename)

        return JSONResponse(content={
            "status": "success",
            "user_prompt": transcript,
            "content": response
        })
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/delete_log")
async def delete_log_by_id(id: str):  # or `id: str` depending on your data type
    try:
        result = await db.delete_call_log(id=id)
        return {"status": "successfully deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return JSONResponse(content={
            "status": "success",
            "content": "healthy asf!"
        })

class UserLogin(BaseModel):
    email: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


@app.post("/login", response_model=Token)
async def login(user: UserLogin):
    user_data = await db.get_user_by_email(user.email)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(user.password, user_data["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(data={"sub": str(user_data["email"])})
    return {"access_token": token, "token_type": "bearer"}


@app.post("/signup")
async def signup(user: UserLogin):
    existing_user = await db.get_user_by_email(user.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed = bcrypt.hashpw(user.password.encode(), bcrypt.gensalt()).decode()

    created = await db.create_user(user.email, hashed)
    if not created:
        raise HTTPException(status_code=500, detail="User creation failed")

    return {"msg": "User created successfully"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)