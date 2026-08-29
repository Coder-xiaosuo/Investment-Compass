"""
FinAgentOS — 共享工具函数
"""
import hashlib
import json
import uuid
from datetime import datetime
from typing import Any, Dict

def generate_trace_id() -> str:
    return f"TXN-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

def sha256_hash(data: Dict[str, Any], previous_hash: str = "") -> str:
    payload_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
    content = previous_hash + payload_str
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

def verify_chain(previous_hash: str, payload: Dict[str, Any], current_hash: str) -> bool:
    return sha256_hash(payload, previous_hash) == current_hash
