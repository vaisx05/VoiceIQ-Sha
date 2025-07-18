from typing import List, Dict, Any
import datetime
from supabase import AsyncClient

class DatabaseHandler:
    def __init__(self, deps):
        self.client : AsyncClient = deps.supabase_client
        self.table : str = "call_logs"
    
    # Create Organisation
    async def create_organisation(self, name: str) -> str:
        response = self.client.table("organisations").insert({"name": name}).execute()
        if response.data and len(response.data) > 0:
            return response.data[0]["id"]
        raise Exception("Failed to create organisation")

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
    async def get_logs_count(self, organisation_id: str):
        response = (
            self.client.table(self.table)
            .select("id", count="exact")
            .eq("organisation_id", organisation_id)
            .execute()
        )
        return response.count or 0
    
    # Get all logs with pagination
    async def get_logs_paginated(self, limit: int, offset: int, organisation_id: str):
        response = (
            self.client.table(self.table)
            .select("id,call_type,call_date,caller_name,toll_free_did,customer_number,report_generated, status,filename")
            .eq("organisation_id", organisation_id)
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
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
    # async def get_transcription(self, uuid: str) -> Dict:
    #     response = self.client.table(self.table).select("transcription").eq("id", uuid).execute()
    #     return response.data[0] or []

    async def get_transcription(self, uuid: str) -> Dict:
        response = self.client.table(self.table).select("transcription").eq("id", uuid).execute()
        if response.data and len(response.data) > 0:
            return response.data[0]
        return {}  # or return None, depending on your usage
    
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

    async def create_user(self, email: str, hashed_password: str, organisation_id: str, role: str) -> bool:
        response = self.client.table("users").insert({
            "email": email,
            "hashed_password": hashed_password,
            "organisation_id": organisation_id,
            "role": role
        }).execute()
        return bool(response.data and len(response.data) > 0)
    
    # Get common questions for an organisation
    async def get_common_questions(self, organisation_id: str) -> List[Dict[str, Any]]:
        response = (
            self.client.table("questions")
            .select("*")
            .eq("is_common", True)
            .eq("organisation_id", organisation_id)
            .execute()
        )
        return response.data if response.data else []

    # Create answer (ensure data contains organisation_id)
    async def create_answer(self, data: Dict[str, Any]) -> Dict:
        print("Completed")
        response = self.client.table("answers").insert(data).execute()
        return response.data[0] if response.data else {}

    # Get answers by callid for an organisation
    async def get_answers_by_callid(self, call_id: str, organisation_id: str) -> List[Dict[str, str]]:
        response = (
            self.client.table("answers")
            .select("questions(question_text),answer_text,call_logs(organisation_id)")
            .eq("call_id", call_id)
            .eq("call_logs.organisation_id", organisation_id)
            .execute()
        )
        if not response.data:
            return []
        return [
            {
                "question_text": item["questions"]["question_text"],
                "answer_text": item["answer_text"]
            }
            for item in response.data
            if item.get("call_logs", {}).get("organisation_id") == organisation_id
        ]
    
    # Delete all answers for a call log
    async def delete_answers_by_callid(self, call_id: str):
        self.client.table("answers").delete().eq("call_id", call_id).execute()

    # Get all questions for an organisation
    async def get_all_questions(self, organisation_id: str) -> List[Dict[str, Any]]:
        response = (
            self.client.table("questions")
            .select("id", "question_text", "is_active")
            .eq("organisation_id", organisation_id)
            .execute()
        )
        return response.data if response.data else []

    # Update question text for an organisation
    async def update_question_text(self, id: str, question_text: str, is_active: bool, organisation_id: str) -> bool:
        response = (
            self.client
            .table("questions")
            .update({
                "question_text": question_text,
                "is_active": is_active        
            })
            .eq("id", id)
            .eq("organisation_id", organisation_id)
            .execute()
        )
        return bool(response.data)  # True if row was updated, False otherwise
    
    # Delete question from an organisation
    async def delete_question(self,id:str,organisation_id: str) -> bool:
        response = (self.client
        .table("questions")
        .delete()
        .eq("id",id)
        .eq("organisation_id",organisation_id)
        .execute()
        )
        return bool (response.data)
    
    # Add question in an organization
    async def add_question(self,question_text:str,organisation_id: str,is_active:bool) -> bool:
        response = (self.client
        .table("questions")
        .insert(
            {
                "question_text":question_text,
                "organisation_id":organisation_id,
                "is_active":is_active
            }
        )
        .execute()
        )
        return bool (response.data)

    # Fetch all organisations
    async def get_all_organisations(self) -> List[Dict]:
        response = self.client.table("organisations").select("*").execute()
        return response.data or []

