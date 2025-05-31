import bcrypt
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List
from agents import deps
from auth import create_access_token, verify_password
from database import DatabaseHandler
from fastapi.middleware.cors import CORSMiddleware
from main import chat, create_initial_log, complete_log_processing
import traceback
import shutil
from uuid import UUID
import os
from datetime import datetime
from transcription import TranscriptionService

db = DatabaseHandler(deps)

transcription_service = TranscriptionService()

app = FastAPI()

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

@app.get("/logs/all")
async def get_all_logs():
    try:
        result = await db.get_all_logs()
        return {"data": result}
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

    try:
        with open(file.filename, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        print("[INFO] TempFile Created.")

        # Step 1: Insert metadata with status='processing'
        log_id = await create_initial_log(file_path=file.filename)

        # Step 2: Kick off processing (could later be pushed to background or a worker)
        await complete_log_processing(file_path=file.filename, log_id=log_id)

        if os.path.exists(file.filename):
            os.remove(file.filename)

        return JSONResponse(content={
            "status": "success",
            "message": "Log uploaded and processing complete",
            "uuid": log_id
        })

    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Internal server error")    

@app.post("/chat")
async def report_chat(req: ChatRequest):
    try:
        response = await chat(user_prompt=req.user_prompt, uuid=req.uuid)
        
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