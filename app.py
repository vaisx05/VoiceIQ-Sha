import bcrypt
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List
from agents import deps
from auth import create_access_token, verify_password
from database import DatabaseHandler
from fastapi.middleware.cors import CORSMiddleware
from main import main, chat
import shutil
from uuid import uuid4, UUID
import os

db = DatabaseHandler(deps)

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

@app.get("/logs/all")
async def get_all_logs():
    try:
        result = await db.get_all_logs()
        return {"data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/logs/{id}")
async def get_all_logs(id: str):  # or `id: str` depending on your data type
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

    try:
        temp_filename = f"temp_{uuid4()}{ext}"

        with open(temp_filename, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        print("✅ TempFile Created.")

        id = await main(file_path=temp_filename)

        if os.path.exists(temp_filename):
            os.remove(temp_filename)

        return JSONResponse(content={
            "status": "success",
            "message" : "Log uploaded successfully",
            "uuid": id
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

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