from pydantic_ai.agent import Agent
from pydantic_ai.providers.google_vertex import GoogleVertexProvider
from pydantic_ai.models.gemini import GeminiModel, LatestGeminiModelNames
from settings import Settings

settings = Settings()

model_name : LatestGeminiModelNames = "gemini-2.5-pro-preview-03-25"

provider = GoogleVertexProvider(
    service_account_info=settings.gcp_service_account_info,
    project_id=settings.gcp_project_id
)

model = GeminiModel(provider=provider,model_name=model_name)

agent = Agent(model=model)

response = agent.run_sync("Hey what's up?")

print(response.output)