from pydantic_settings import BaseSettings
from pydantic import Field
import json
import base64
from typing import Dict, Any

class Settings(BaseSettings):
    groq_api_key : str = Field(..., validation_alias="GROQ_API_KEY")
    supabase_url : str = Field(..., validation_alias="SUPABASE_URL")
    supabase_key : str = Field(..., validation_alias="SUPABASE_KEY")
    logfire_write_token : str = Field(..., validation_alias="LOGFIRE_WRITE_TOKEN")
    aws_access_key: str = Field(..., validation_alias="AWS_ACCESS_KEY")
    aws_secret_access_key: str = Field(..., validation_alias="AWS_SECRET_ACCESS_KEY")
    # gcp_service_account_json_base64: str = Field(..., validation_alias="GCP_SERVICE_ACCOUNT_JSON_BASE64")
    # gcp_project_id: str = Field(..., validation_alias="GCP_PROJECT_ID")
    
    # @property
    # def gcp_service_account_info(self) -> Dict[str, Any]:
    #     """Decodes the base64 string and returns the service account info as a dict."""
    #     if not self.gcp_service_account_json_base64:
    #         raise ValueError("GCP_SERVICE_ACCOUNT_JSON_BASE64 is not set.")
    #     try:
    #         decoded_json = base64.b64decode(self.gcp_service_account_json_base64).decode('utf-8')
    #         return json.loads(decoded_json)
    #     except (base64.binascii.Error, json.JSONDecodeError) as e:
    #         raise ValueError(f"Failed to decode or parse GCP_SERVICE_ACCOUNT_JSON_BASE64: {e}")

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'