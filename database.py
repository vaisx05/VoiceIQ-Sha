from typing import List, Dict, Any

class DatabaseHandler:
    def __init__(self, deps):
        self.client = deps.supabase_client
        self.table = "call_logs"

    # Create
    async def create_call_log(self, data: Dict[str, Any]) -> Dict:
        response = await self.client.table(self.table).insert(data).execute()
        return response.data[0] if response.data else {}

    # Get all columns, limited rows
    async def get_all_logs(self, limit: int) -> List[Dict]:
        response = await self.client.table(self.table).select("*").limit(limit).execute()
        return response.data or []

    # Get specific columns, limited rows
    async def get_columns(self, columns: List[str], limit: int) -> List[Dict]:
        column_str = ", ".join(columns)
        response = await self.client.table(self.table).select(column_str).limit(limit).execute()
        return response.data or []

    # Update
    async def update_call_log(self, call_id: str, update_data: Dict[str, Any]) -> Dict:
        response = await self.client.table(self.table).update(update_data).eq("id", call_id).execute()
        return response.data[0] if response.data else {}

    # Delete
    async def delete_call_log(self, call_id: str) -> bool:
        response = await self.client.table(self.table).delete().eq("id", call_id).execute()
        return bool(response.data)
