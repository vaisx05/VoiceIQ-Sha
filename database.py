from typing import List, Dict, Any
import datetime
from supabase import AsyncClient

class DatabaseHandler:
    def __init__(self, deps):
        self.client : AsyncClient = deps.supabase_client
        self.table : str = "call_logs"

    # Create
    async def create_call_log(self, data: Dict[str, Any]) -> Dict:
        response = self.client.table(self.table).insert(data).execute()
        return response.data[0] if response.data else {}

    # Get all columns, limited rows
    async def get_all_logs(self) -> List[Dict]:
        response = self.client.table(self.table).select("id,call_type,call_date,caller_name,toll_free_did,customer_number,report_generated, status, filename").order("created_at", desc=True).execute()
        return response.data or []
    
    async def get_log(self, id: str) -> List[Dict]:
        response = self.client.table(self.table).select("*").eq("id",id).order("created_at", desc=True).execute()
        return response.data or []
    # get count
    def get_logs_count(self):
        response = self.client.table(self.table).select("id", count="exact").execute()
        return response.count or 0

    # Get all logs with pagination
    def get_logs_paginated(self, limit: int, offset: int):
        response = self.client.table(self.table) \
            .select("id,call_type,call_date,caller_name,toll_free_did,customer_number,report_generated, status,filename") \
            .order("created_at", desc=True) \
            .range(offset, offset + limit - 1) \
            .execute()
        return response.data or []

    
    # Get specific columns, limited rows
    async def get_columns(self, columns: List[str], limit: int) -> List[Dict]:
        column_str = ", ".join(columns)
        response = self.client.table(self.table).select(column_str).limit(limit).execute()
        return response.data or []

    # Get report by uuid
    async def get_report(self, uuid: str) -> Dict:
        response = self.client.table(self.table).select("report_generated").eq("id", uuid).execute()
        return response.data or []
    
    # Get transcription by uuid
    async def get_transcription(self, uuid: str) -> Dict:
        response = self.client.table(self.table).select("transcription").eq("id", uuid).execute()
        return response.data[0] or []
    
    async def get_all_by_dates(self, start_date: datetime, end_date: datetime) -> List[Dict]:
        response = (
            self.client.table(self.table)
            .select("*")
            .gte("call_date", start_date.isoformat())
            .lte("call_date", end_date.isoformat())
            .order("call_date", desc=True)
            .execute()
        )
        return response.data or []

    async def file_exists(self, filename: str) -> bool:
        response = self.client.table(self.table).select("id").eq("filename", filename).execute()
        return bool(response.data)

    # Update
    async def update_call_log(self, call_id: str, update_data: Dict[str, Any]) -> Dict:
        response = self.client.table(self.table).update(update_data).eq("id", call_id).execute()
        return response.data[0] if response.data else {}

    # Delete
    async def delete_call_log(self, id: str) -> bool:
        response = self.client.table(self.table).delete().eq("id", id).execute()
        return bool(response.data)


    # User stuff
    async def get_user_by_email(self, email: str) -> Dict:
        response = self.client.table("users").select("*").eq("email", email).execute()
        return response.data[0] if response.data else {}

    async def create_user(self, email: str, hashed_password: str) -> bool:
        response = self.client.table("users").insert({
            "email": email,
            "hashed_password": hashed_password
        }).execute()
        return response.data[0] if response.data else {}

        
