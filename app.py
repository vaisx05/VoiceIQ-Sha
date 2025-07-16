import bcrypt
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query, Depends
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer
from filename_parser import parse_call_filename
from upload_filename_parser import upload_parse_call_filename
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from agents import deps
from auth import create_access_token, verify_password, SECRET_KEY, ALGORITHM
from jose import jwt, JWTError
from database import DatabaseHandler
from fastapi.middleware.cors import CORSMiddleware
from main import chat, process_log, upload_process_log
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
    #region_name="us-east-1"  # Adjust region as needed
)

BUCKET_NAME = "call-logs-audio-files" 

db = DatabaseHandler(deps)

transcription_service = TranscriptionService(bucket_name=BUCKET_NAME)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        organisation_id = payload.get("organisation_id")
        role = payload.get("role")
        if email is None or organisation_id is None or role is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"email": email, "organisation_id": organisation_id, "role": role}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

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

# search elements in database
class SearchRequest(BaseModel):
    filters: Optional[Dict[str, str]] = None 
    limit: int = 20
    offset: int = 0

# --- Models for super admin actions ---
class OrganisationCreate(BaseModel):
    name: str

class UserCreate(BaseModel):
    email: str
    password: str
    organisation_id: str
    role: str  # 'admin' or 'user'  

@app.post("/admin/create_organisation")
async def create_organisation(
    org: OrganisationCreate,
    user=Depends(get_current_user)
):
    if user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    org_id = await db.create_organisation(org.name)
    return {"msg": "Organisation created", "organisation_id": org_id}

@app.post("/admin/create_user")
async def create_user(
    user_req: UserCreate,
    user=Depends(get_current_user)
):
    # Only super_admin or admin can create users
    if user["role"] not in ["super_admin", "admin"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # super_admin can only create admins for any organisation
    if user["role"] == "super_admin":
        if user_req.role != "admin":
            raise HTTPException(status_code=403, detail="Super admin can only create admins")
    
    # admin can only create users for their own organisation, and only with role 'user'
    if user["role"] == "admin":
        if user_req.organisation_id != user["organisation_id"]:
            raise HTTPException(status_code=403, detail="Admins can only create users for their own organisation")
        if user_req.role != "user":
            raise HTTPException(status_code=403, detail="Admins can only create users with role 'user'")
    
    existing_user = await db.get_user_by_email(user_req.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed = bcrypt.hashpw(user_req.password.encode(), bcrypt.gensalt()).decode()
    created = await db.create_user(
        user_req.email, hashed, user_req.organisation_id, user_req.role
    )
    if not created:
        raise HTTPException(status_code=500, detail="User creation failed")
    return {"msg": "User created successfully"}

@app.post("/logs/date")
async def get_all_by_dates(req: Dates):
    try:
        call_logs = await db.get_all_by_dates(req.from_date, req.to_date)
        return {"data": call_logs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/logs/all")
async def get_all_logs(
    limit: int = Query(30, gt=0),
    offset: int = Query(0, ge=0),
    user=Depends(get_current_user)
):
    data = await db.get_logs_paginated(
        limit=limit,
        offset=offset,
        organisation_id=user["organisation_id"]
    )
    total = await db.get_logs_count(organisation_id=user["organisation_id"])
    return {
        "data": data,
        "limit": limit,
        "offset": offset,
        "total": total
    }

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
async def create_log(
    file: UploadFile = File(...),
    user=Depends(get_current_user)
):
    allowed_exts = (".wav", ".mp3")
    ext = os.path.splitext(file.filename)[-1].lower()

    if ext not in allowed_exts:
        raise HTTPException(status_code=400, detail="Only .wav or .mp3 files are supported")

    if await db.file_exists(file.filename):
        raise HTTPException(status_code=409, detail="File with this name already uploaded")
    
    # Parse metadata from filename
    metadata = await parse_call_filename(file.filename)
    
    # Insert initial row in Supabase with metadata, status, and organisation_id
    initial_payload = {
        **metadata,
        "status": "processing",
        "organisation_id": user["organisation_id"],  # <-- Add this line
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
    # from main import process_log
    payload = await process_log(filename)
    update_data = {**payload, "status": "complete"}
    await db.update_call_log(log_id, update_data)

# async def process_and_update_log(filename: str, log_id: str, parser: str = "strict"):
#     if parser == "upload":
#         from upload_filename_parser import upload_parse_call_filename
#         payload = await upload_parse_call_filename(filename)
#     else:
#         from filename_parser import parse_call_filename
#         payload = await parse_call_filename(filename)
#     update_data = {**payload, "status": "complete"}
#     await db.update_call_log(log_id, update_data)

# data filtering by date range
@app.post("/logs/datefilter")
async def filter_logs_by_date(req: Dict[str, Any], user=Depends(get_current_user)):
    try:
        filters = req.get("datefilter", {})
        call_date_from = filters.get("call_date_from")
        call_date_to = filters.get("call_date_to")
        limit = req.get("limit", 20)
        offset = req.get("offset", 0)

        columns = "id,call_type,call_date,caller_name,toll_free_did,customer_number,report_generated, status, filename, organisation_id"
        query = db.client.table(db.table).select(columns)
        query = query.eq("organisation_id", user["organisation_id"])  # <-- filter by organisation

        if call_date_from:
            query = query.gte("call_date", call_date_from)
        if call_date_to:
            query = query.lte("call_date", call_date_to)

        total_query = db.client.table(db.table).select("id", count="exact")
        total_query = total_query.eq("organisation_id", user["organisation_id"])  # <-- filter by organisation
        if call_date_from:
            total_query = total_query.gte("call_date", call_date_from)
        if call_date_to:
            total_query = total_query.lte("call_date", call_date_to)
        total_result = total_query.execute()
        total_count = total_result.count or 0

        query = query.order("created_at", desc=False).range(offset, offset + limit - 1)
        result = query.execute()

        return {
            "data": result.data or [],
            "limit": limit,
            "offset": offset,
            "total": total_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))  

# Search logs with filters and sorting
@app.post("/logs/searching")
async def search_logs(req: Dict[str, Any], user=Depends(get_current_user)):
    try:
        filters = req.get("filters", {})
        sort = req.get("sort", {})
        limit = req.get("limit", 20)
        offset = req.get("offset", 0)

        columns = "id,call_date,call_type,caller_name,status,filename,customer_number,toll_free_did, organisation_id"
        query = db.client.table(db.table).select(columns)
        query = query.eq("organisation_id", user["organisation_id"])  # <-- filter by organisation

        def apply_filters(query, filters):
            if filters.get("call_date"):
                query = query.eq("call_date", filters["call_date"])
            if filters.get("call_type"):
                query = query.eq("call_type", filters["call_type"])
            if filters.get("caller_name"):
                query = query.ilike("caller_name", f"%{filters['caller_name']}%")
            if filters.get("customer_number"):
                query = query.ilike("customer_number", f"%{filters['customer_number']}%")
            if filters.get("toll_free_did"):
                query = query.ilike("toll_free_did", f"%{filters['toll_free_did']}%")
            if filters.get("status"):
                query = query.ilike("status", f"%{filters['status']}%")
            return query

        query = apply_filters(query, filters)

        total_query = db.client.table(db.table).select("id", count="exact")
        total_query = total_query.eq("organisation_id", user["organisation_id"])  # <-- filter by organisation
        total_query = apply_filters(total_query, filters)
        total_result = total_query.execute()
        total_count = total_result.count or 0

        sort_column = sort.get("column", "created_at")
        sort_direction = sort.get("direction", "desc")
        query = query.order(sort_column, desc=(sort_direction == "desc"))

        query = query.range(offset, offset + limit - 1)
        result = query.execute()

        return {
            "data": result.data or [],
            "limit": limit,
            "offset": offset,
            "total": total_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat")
async def report_chat(
    ctx: ChatRequest,
    user=Depends(get_current_user)
):
    try:
        response = await chat(
            user_prompt=ctx.user_prompt,
            uuid=ctx.uuid,
            organisation_id=user["organisation_id"]
        )
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

@app.delete("/delete_log")
async def delete_log_by_id(id: str):  # or `id: str` depending on your data type
    try:
        # Delete all answers for this call log first
        await db.delete_answers_by_callid(id)
        # Now delete the call log
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
        # if not verify_password(user.password, user_data["hashed_password"]):
        #     raise HTTPException(status_code=401, detail="Invalid credentials")
        token = create_access_token(data={
            "sub": str(user_data["email"]),
            "organisation_id": str(user_data["organisation_id"]),
            "role": str(user_data["role"])
        })
        return {"access_token": token, "token_type": "bearer"}

@app.post("/signup")
async def signup(user: UserLogin):
    existing_user = await db.get_user_by_email(user.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed = bcrypt.hashpw(user.password.encode(), bcrypt.gensalt()).decode()

    created = await db.create_user(user.email, hashed   )
    if not created:
        raise HTTPException(status_code=500, detail="User creation failed")

    return {"msg": "User created successfully"}

@app.post("/upload")
async def upload_any_file(
    file: UploadFile = File(...),
    user=Depends(get_current_user)  # <-- Add this line
):
    filename = file.filename
    name, ext = os.path.splitext(filename)
    if not ext:
        ext = ".wav, .mp3"  # Default to .wav or .mp3 as needed
        filename = filename + ext

    if await db.file_exists(filename):
        raise HTTPException(status_code=409, detail="File with this name already uploaded")

    metadata = await upload_parse_call_filename(filename)

    initial_payload = {
        **metadata,
        "status": "processing",
        "organisation_id": user["organisation_id"],  # <-- Add this line
    }   

    initial_row = await db.create_call_log(initial_payload)
    log_id = initial_row["id"] 
    
    try:
        file_data = await file.read()

        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=filename,
            Body=file_data,
            ContentType=file.content_type
        )

        asyncio.create_task(upload_process_and_update_log(filename, log_id, db))

        return JSONResponse(content={
            "status": "success",
            "message": "File uploaded and processing complete",
            "uuid": log_id
        })

    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Internal server error")
    

# Add this function to handle background processing and update
async def upload_process_and_update_log(filename: str, log_id: str, db):
    log_list = await db.get_log(log_id)
    log = log_list[0] if log_list else None

    if log:
        organisation_id = log["organisation_id"]
        common_questions = await db.get_common_questions(organisation_id)
        payload = await upload_process_log(filename, log_id, organisation_id, db)
        update_data = {**payload, "status": "complete"}
        await db.update_call_log(log_id, update_data)
    else:
        # handle log not found
        print(f"Log with id {log_id} not found.")
        # Optionally, raise an exception or return an error response


# Pydantic model
class Question(BaseModel):
    question_text: str
    is_active: Optional[bool] = True
    is_common: Optional[bool] = True  

@app.get("/get_answers/{call_id}")
async def get_answers(call_id: str, user=Depends(get_current_user)):
    callresults = await db.get_answers_by_callid(call_id=call_id, organisation_id=user["organisation_id"])
    return callresults

@app.get("/get_all_questions")
async def get_all_questions(user=Depends(get_current_user)):
    questions = await db.get_all_questions(organisation_id=user["organisation_id"])
    return questions

@app.put("/update_question/{id}")
async def update_question(id: str, question_text: str, is_active: bool, user=Depends(get_current_user)):
    question_updated = await db.update_question_text(id, question_text, is_active, organisation_id=user["organisation_id"])
    if not question_updated:
        raise HTTPException(status_code=404, detail="Question not found")
    return {"message": "Question updated successfully"}

@app.delete("/delete_question/{id}")
async def delete_question(id:str, user = Depends(get_current_user)):
    question_deleted = await db.delete_question(id, organisation_id=user["organisation_id"])
    if not question_deleted:
        raise HTTPException(status_code=404, detail="Question not found")
    return {"message": "Question deleted successfully"}

@app.post("/add_question")
async def add_question(question: Question, user=Depends(get_current_user), 
                       is_common: bool = True):
    question_added = await db.add_question(
        question_text=question.question_text,
        organisation_id=user["organisation_id"],
        is_active=question.is_active,
        is_common=True
    )
    return {"success": question_added}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)