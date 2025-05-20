from dataclasses import dataclass

from pydantic_ai import Agent
from pydantic_ai.models.gemini import GeminiModelSettings, GeminiModel, GeminiModelName, LatestGeminiModelNames
from pydantic_ai.providers.google_vertex import GoogleVertexProvider
from pydantic import BaseModel, Field
from supabase import Client, create_client
import groq

from settings import Settings

settings = Settings()

async_groq_client = groq.AsyncGroq(api_key=settings.groq_api_key)

gemini_settings = GeminiModelSettings(
    temperature=0.7,
    top_p=0.95,
    frequency_penalty=0,
)

provider = GoogleVertexProvider(
    service_account_info=settings.gcp_service_account_info,
    project_id=settings.gcp_project_id
)

report_model_name: GeminiModelName = "gemini-2.5-pro-preview-05-06"

general_model_name: GeminiModelName = "gemini-2.0-flash"

report_model = GeminiModel(
    model_name=report_model_name,
    provider=provider
)

general_model = GeminiModel(
    model_name=general_model_name,
    provider=provider
)


class Form(BaseModel):
    responder_name: str = Field(description="The first name of the responder attending to the request, if given, else return 'null'")
    caller_name: str = Field(description="The first name of the caller making the request if given, else return 'null'")
    request_type: str = Field(description="The type of request being made out of the list: [technical support, billing, new connection]")
    issue_summary: str = Field(description="Detailed description of 50 lines of the issue being reported by the caller")
    caller_sentiment: str = Field(description="The emotion of the customer to be given in one word out of the list: [happy, sad, angry, frustrated]")

@dataclass
class Deps:
    supabase_url: str = settings.supabase_url
    supabase_key: str = settings.supabase_key
    supabase_client: Client = create_client(supabase_key=supabase_key, supabase_url=supabase_url)
    
deps = Deps()

with open("prompts/report_agent_prompt.txt", "r") as file:
    report_agent_prompt = file.read()

with open("prompts/call_log_agent_prompt.txt", "r") as file:
    call_log_agent_prompt = file.read()

with open("prompts/database_agent_prompt.txt", "r") as file:
    database_agent_prompt = file.read()

with open("prompts/chat_agent_prompt.txt", "r") as file:
    chat_agent_prompt = file.read()

report_agent = Agent(
    model=report_model,
    model_settings=gemini_settings,
    system_prompt=report_agent_prompt,
    retries=3,
)

call_log_agent = Agent(
    model=general_model,
    model_settings=gemini_settings,
    system_prompt=call_log_agent_prompt,
    retries=3,
)

database_agent = Agent(
    model=general_model,
    model_settings=gemini_settings,
    system_prompt=database_agent_prompt,
    retries=3,
    output_type=Form
)

chat_agent = Agent(
    model=general_model,
    model_settings=gemini_settings,
    system_prompt=chat_agent_prompt,
    retries=3
)
