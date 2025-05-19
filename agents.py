from dataclasses import dataclass

from pydantic_ai import Agent
from pydantic_ai.models.groq import GroqModelSettings, GroqModel, GroqModelName
from pydantic_ai.providers.groq import GroqProvider
import groq
from pydantic_ai.models.gemini import GeminiModelSettings, GeminiModel, GeminiModelName
from pydantic_ai.providers.google_gla import GoogleGLAProvider
from pydantic import BaseModel, Field
from supabase import Client, create_client

from settings import Settings

settings = Settings()

# Groq Model Definition
groq_settings = GroqModelSettings(
    temperature=0.7,
    top_p=0.95,
    frequency_penalty=0,
)

groq_model_name : GroqModelName = "llama-3.3-70b-versatile"

async_groq_client = groq.AsyncGroq(api_key=settings.groq_api_key)

groq_model = GroqModel(
    model_name=groq_model_name,
    provider=GroqProvider(groq_client=async_groq_client),
)

# Gemini Model Definition
gemini_settings = GeminiModelSettings(
    temperature=0.7,
    top_p=0.95,
    frequency_penalty=0,
)

gemini_model_name : GeminiModelName = "gemini-2.5-pro-preview-05-06"

gemini_model = GeminiModel(
    model_name=gemini_model_name,
    provider=GoogleGLAProvider(api_key=settings.gemini_api_key)
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

with open("prompts/call_log_agent_prompt.txt", "r") as file:
    call_log_agent_prompt = file.read()

with open("prompts/report_agent_prompt.txt", "r") as file:
    report_agent_prompt = file.read()

with open("prompts/database_agent_prompt.txt", "r") as file:
    database_agent_prompt = file.read()

with open("prompts/chat_agent_prompt.txt", "r") as file:
    chat_agent_prompt = file.read()

call_log_agent = Agent(
    model=groq_model,
    model_settings=groq_settings,
    system_prompt=call_log_agent_prompt,
    retries=3,
)

report_agent = Agent(
    model=gemini_model,
    model_settings=gemini_settings,
    system_prompt=report_agent_prompt,
    retries=3,
)

database_agent = Agent(
    model=groq_model,
    model_settings=groq_settings,
    system_prompt=database_agent_prompt,
    retries=3,
    output_type=Form
)

chat_agent = Agent(
    model=groq_model,
    model_settings=groq_settings,
    system_prompt=chat_agent_prompt,
    retries=3
)
