from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    
    groq_api_key : str = Field(..., validation_alias="GROQ_API_KEY")
    gemini_api_key : str = Field(..., validation_alias="GEMINI_API_KEY")
    supabase_url : str = Field(..., validation_alias="SUPABASE_URL")
    supabase_key : str = Field(..., validation_alias="SUPABASE_KEY")
    
    class Config:
        env_file = ".env"

