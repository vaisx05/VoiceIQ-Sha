from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    
    groq_api_key : str = Field(..., validation_alias="GROQ_API_KEY")
    gemini_api_key : str = Field(..., validation_alias="GEMINI_API_KEY")
    supabase_key : str = Field(..., validation_alias="SUPABASE_KEY")
    supabase_url :str = Field(..., validation_alias="SUPABASE_URL")
    
    class Config:
        env_file = ".env"

# --- Database Schema Reference (Supabase) ---
# Table: call_logs
# Columns:
# - id (UUID, primary key)
# - responder_name (text, required)
# - caller_name (text, optional)
# - request_type (text, required)
# - issue_summary (text, required)
# - caller_sentiment (text, required)
# - report_generated (text, required)
# - call_log (text, required)
# ---------------------------------------------
