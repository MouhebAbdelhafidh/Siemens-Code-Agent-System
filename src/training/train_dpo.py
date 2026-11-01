import os
import torch
from datasets import load_dataset
from peft import LoraConfig
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)
from trl import DPOConfig, DPOTrainer

# 1. Configuration & Paths
BASE_DIR = r"C:\Users\mouhe\Desktop\industrial-mcp-agent"
DATASET_PATH = os.path.join(BASE_DIR, "dpo_dataset.jsonl")
OUTPUT_DIR = os.path.join(BASE_DIR, "qwen_scl_dpo_checkpoint")
MODEL_ID = "Qwen/Qwen2.5-Coder-7B-Instruct"

print(f"[DPO Trainer] Loading dataset from: {DATASET_PATH}")
if not os.path.exists(DATASET_PATH):
    raise FileNotFoundError(
        f"Dataset not found at {DATASET_PATH}. Run some agent generations first"
        " to log preference pairs!"
    )

# 2. Load Dataset for DPO (expects 'prompt', 'chosen', 'rejected' keys)
dataset = load_dataset("json", data_files=DATASET_PATH, split="train")

# 3. Configure 4-bit Quantization
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
)

print(f"[DPO Trainer] Loading base model: {MODEL_ID}")
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
tokenizer.pad_token = tokenizer.eos_token
tokenizer.padding_side = "left"  # TRL 1.17 requires left-padding

model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    quantization_config=bnb_config,
    device_map={"": 0},
    trust_remote_code=True,
)

# 4. Configure LoRA
peft_config = LoraConfig(
    r=16,
    lora_alpha=32,
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ],
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
)

# 5. DPO Training Arguments
# In TRL 1.17, max_length lives in DPOConfig. max_prompt_length is GONE.
# Truncation is controlled via max_length + truncation_mode only.
training_args = DPOConfig(
    per_device_train_batch_size=1,
    gradient_accumulation_steps=4,
    learning_rate=5e-6,
    logging_steps=1,
    num_train_epochs=3,
    output_dir=OUTPUT_DIR,
    save_strategy="epoch",
    bf16=True,
    optim="paged_adamw_8bit",
    report_to="none",
    max_length=2048,            # total sequence length (prompt + completion)
    truncation_mode="keep_start",  # only supported mode in TRL 1.17
)

# 6. Initialize DPOTrainer
# Note: 'processing_class' replaces 'tokenizer' in TRL 1.17
dpo_trainer = DPOTrainer(
    model=model,
    ref_model=None,
    args=training_args,
    train_dataset=dataset,
    processing_class=tokenizer,
    peft_config=peft_config,
)

print("[DPO Trainer] Starting DPO training loop...")
dpo_trainer.train()

# 7. Save the Aligned LoRA Adapters
adapter_output_path = os.path.join(BASE_DIR, "aligned_industrial_qwen_adapter")
dpo_trainer.model.save_pretrained(adapter_output_path)
tokenizer.save_pretrained(adapter_output_path)

print(f"[DPO Trainer] Training complete! Adapters saved to: {adapter_output_path}")