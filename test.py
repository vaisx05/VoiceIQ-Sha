from pydantic_ai.agent import Agent
from pydantic_ai.providers.google_vertex import GoogleVertexProvider
from pydantic_ai.models.gemini import GeminiModel, LatestGeminiModelNames
import json

model_name : LatestGeminiModelNames = "gemini-2.5-pro-preview-03-25"

file_path = "gen-lang-client-0778861942-8dc36047746a.json"

with open(file_path, "r") as f:
    data = json.load(f)     
    json_str = json.dumps(data)

print(json_str)

provider = GoogleVertexProvider(
    service_account_info=json_str,
    project_id="gen-lang-client-0778861942"
)

model = GeminiModel(provider=provider,model_name=model_name)

agent = Agent(model=model)

response = agent.run_sync("Hey what's up?")

print(response.output)