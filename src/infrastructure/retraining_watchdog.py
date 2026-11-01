import os
import subprocess
import time

DATASET_PATH = r"C:\Users\mouhe\Desktop\industrial-mcp-agent\dpo_dataset.jsonl"
THRESHOLD = 50  # Retrain every 50 new preference pairs

def get_dataset_line_count():
    if not os.path.exists(DATASET_PATH):
        return 0
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        return sum(1 for _ in f)

def run_pipeline():
    print("[Watchdog] Threshold reached! Initiating automated DPO retraining cycle...")
    
    # 1. Run DPO training
    subprocess.run(["python", "train_dpo.py"], check=True)
    
    # 2. Merge adapters
    subprocess.run(["python", "merge_adapter.py"], check=True)
    
    # 3. Update Ollama model
    subprocess.run(["ollama", "create", "aligned-scl-coder", "-f", "./Modelfile"], check=True)
    
    # 4. Run regression suite
    result = subprocess.run(["pytest", "pytest_industrial.py", "-v"])
    if result.returncode == 0:
        print("[Watchdog] Retraining and regression validation completed successfully!")
    else:
        print("[Watchdog] Warning: Regression suite failed on newly trained adapter.")

if __name__ == "__main__":
    print("[Watchdog] MLOps automated retraining monitor active...")
    last_count = get_dataset_line_count()
    
    while True:
        current_count = get_dataset_line_count()
        if current_count >= last_count + THRESHOLD:
            run_pipeline()
            last_count = current_count
        time.sleep(300)  # Check every 5 minutes