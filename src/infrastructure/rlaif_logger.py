import json
import os

# Absolute path configuration matching your workspace
BASE_DIR = r"C:\Users\mouhe\Desktop\industrial-mcp-agent"
DATASET_PATH = os.path.join(BASE_DIR, "dpo_dataset.jsonl")


def log_preference_pair(prompt: str, rejected_code: str, chosen_code: str) -> None:
  """Automatically logs RLAIF preference pairs (rejected vs chosen)

  into a local JSONL dataset for subsequent DPO fine-tuning.
  """
  os.makedirs(BASE_DIR, exist_ok=True)

  entry = {"prompt": prompt, "chosen": chosen_code, "rejected": rejected_code}

  with open(DATASET_PATH, "a", encoding="utf-8") as f:
    f.write(json.dumps(entry) + "\n")

  print(f"[RLAIF Logger] Preference pair successfully appended to {DATASET_PATH}")