import hashlib
import json
import os
from datetime import datetime

LEDGER_PATH = r"C:\Users\mouhe\Desktop\industrial-mcp-agent\production_audit_ledger.jsonl"

def record_audit_event(prompt: str, fingerprint: str, model_version: str, verification_status: dict) -> str:
    """Appends a cryptographically hash-chained event to the immutable industrial audit ledger."""
    
    # Read previous block hash to establish cryptographic chain
    prev_hash = "0000000000000000000000000000000000000000000000000000000000000000"
    if os.path.exists(LEDGER_PATH):
        with open(LEDGER_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
            if lines:
                last_record = json.loads(lines[-1].strip())
                prev_hash = last_record.get("current_hash", prev_hash)

    event_payload = {
        "timestamp": datetime.utcnow().isoformat(),
        "model_version": model_version,
        "prompt_vector": prompt,
        "scl_fingerprint": fingerprint,
        "verification_status": verification_status,
        "previous_block_hash": prev_hash
    }

    # Compute SHA-256 hash of this record including previous hash (Hash Chain)
    serialized = json.dumps(event_payload, sort_keys=True)
    current_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    
    event_payload["current_hash"] = current_hash

    with open(LEDGER_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(event_payload) + "\n")

    return current_hash