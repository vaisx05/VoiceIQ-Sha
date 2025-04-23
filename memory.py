from typing import Any, List
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    UserPromptPart,
    TextPart,
)

class MemoryHandler:
    def __init__(self, deps):
        self.client = deps.supabase_client
        self.table = "memory"

    async def _message_handler(self, response: List[Any]) -> List[ModelMessage]:
        messages: List[ModelMessage] = []

        for item in response:
            role = item["role"]
            content = item["content"]

            if role == "user":
                messages.append(ModelRequest(parts=[UserPromptPart(content=content)]))
            elif role == "bot":
                messages.append(ModelResponse(parts=[TextPart(content=content)]))
        return messages

    async def get_memory(self, user_id: str, limit: int) -> List[ModelMessage]:

        # Fetch the latest messages from Supabase
        response = (
            self.client.table(self.table)
            .select("role, content")
            .eq("user_id", user_id)
            .order("timestamp", desc=True)
            .limit(limit)
            .execute()
        )
        response = list(reversed(response.data))  # Reverse for chronological order

        messages = await self._message_handler(response)

        return messages

    async def append_message(self, user_id: str, role: str, content: str) -> None:
        
        payload = {
                "user_id": user_id,
                "role": role,
                "content": content,
                }
        self.client.table("memory").insert(payload).execute()
