from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List
from agents import deps
from database import DatabaseHandler
from fastapi.middleware.cors import CORSMiddleware
from main import main, chat
import shutil
from uuid import  uuid4
import os

db = DatabaseHandler(deps)

app = FastAPI()

origins = [
    "http://localhost:3000",  # your frontend
    "http://127.0.0.1:3000",  # optional, in case you access it via 127.0.0.1
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # must match exactly
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    user_prompt: str
    uuid: uuid4

# Pydantic model for /logs/columns POST request
class ColumnRequest(BaseModel):
    columns: List[str] | str
    limit: int

@app.get("/logs/all/{limit}")
async def get_all_logs(limit: int):
    try:
        result = await db.get_all_logs(limit)
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

        await main(file_path=temp_filename)

        if os.path.exists(temp_filename):
            os.remove(temp_filename)

        return JSONResponse(content={
            "status": "success",
            "message" : "Log uploaded successfully"
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@app.post("/chat")
async def report_chat(request: ChatRequest):
    try:
        response = await chat(user_prompt=request.user_prompt, uuid=request.uuid)
        
        return JSONResponse(content={
            "status": "success",
            "content": response
        })
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)