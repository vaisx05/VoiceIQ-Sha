from datetime import datetime
from typing import Optional

async def parse_call_filename(filename: str) -> dict:
    base = filename.split('.')[0]
    parts = base.split('-')
    
    if len(parts) != 6:
        raise ValueError(f"Invalid filename format: {filename}")
    
    call_type = parts[0]
    raw_date = parts[3]
    raw_time = parts[4]
    
    call_date = datetime.strptime(raw_date, "%Y%m%d").date().isoformat()
    call_start_time = datetime.strptime(raw_time, "%H%M%S").time().isoformat()  # ISO 8601 time format
    
    result = {
        "filename": filename,
        "call_type": call_type,
        "toll_free_did": None,
        "agent_extension": None,
        "customer_number": parts[2],
        "call_date": call_date,
        "call_start_time": call_start_time,
        "call_id": parts[5],
    }

    if call_type == "in":
        result["toll_free_did"] = parts[1]
    elif call_type == "external":
        result["agent_extension"] = parts[1]
    else:
        raise ValueError(f"Unknown call type: {call_type}")
    
    return result
