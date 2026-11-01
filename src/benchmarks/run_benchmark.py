import json
import os
import sys
import ollama

# Ensure project root is in PYTHONPATH
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.industrial_server import generate_scl_with_rag, validate_scl_structure, validate_scl_data_flow_paths

BENCHMARK_PATH = os.path.join(os.path.dirname(__file__), "industrial_benchmarks.json")

def ai_validate_scl_code(prompt: str, scl_code: str) -> bool:
    """
    Uses an independent LLM critic agent to semantically validate whether 
    the generated SCL code correctly fulfills the prompt and adheres to Siemens standards.
    """
    critic_prompt = (
        "You are an expert Siemens SCL Industrial Automation Auditor. "
        "Evaluate whether the following generated SCL code correctly and safely satisfies the user prompt "
        "and complies with IEC 61131-3 standards (no METHOD blocks, proper variables, correct logic).\n\n"
        f"USER PROMPT:\n{prompt}\n\n"
        f"GENERATED SCL CODE:\n{scl_code}\n\n"
        "Output ONLY 'AI_VALIDATION_PASSED' if the code is syntactically sound, logically correct, and safe, "
        "or 'AI_VALIDATION_FAILED: <reason>' if it violates requirements."
    )
    
    try:
        response = ollama.chat(
            model="qwen2.5-coder:7b",
            messages=[{"role": "user", "content": critic_prompt}]
        )
        feedback = response["message"]["content"].strip()
        print(f"    - AI Auditor Verdict: {feedback.splitlines()[0]}")
        return "AI_VALIDATION_PASSED" in feedback
    except Exception as e:
        print(f"    - AI Auditor Error: {e}")
        return False

def run_evaluation():
    if not os.path.exists(BENCHMARK_PATH):
        print(f"[Benchmark Error] Benchmark file not found at {BENCHMARK_PATH}")
        return

    with open(BENCHMARK_PATH, "r", encoding="utf-8") as f:
        benchmarks = json.load(f)

    total_tests = len(benchmarks)
    pass_at_1 = 0
    pass_at_k = 0

    print(f"\n==========================================")
    print(f"Starting SCL-Eval-Industrial Suite with AI Auditor ({total_tests} tests)")
    print(f"==========================================\n")

    for test in benchmarks:
        test_id = test["id"]
        prompt = test["prompt"]
        print(f"\nRunning [{test_id}]: {prompt[:65]}...")

        # Execute generation & RLEF loop
        result_output = generate_scl_with_rag(prompt)

        # Robust SCL code extraction from markdown block
        # Robust SCL code extraction from markdown block
        scl_code = result_output
        if "```scl" in result_output:
            parts = result_output.split("```scl")
            if len(parts) > 1:
                scl_code = parts[1].split("```")[0].strip()
        elif "```" in result_output:
            parts = result_output.split("```")
            if len(parts) > 1:
                code_block = parts[1].strip()
                if code_block.startswith("scl"):
                    code_block = code_block[3:].strip()
                scl_code = code_block.split("```")[0].strip()

        # 1. Deterministic Structural Check
        struct_check = validate_scl_structure(scl_code)
        is_struct_passed = "PASSED" in struct_check or "SUCCESS" in struct_check

        # 2. Deterministic Data-Flow Check
        dataflow_check = validate_scl_data_flow_paths(scl_code)
        is_dataflow_passed = "SUCCESS" in dataflow_check

        # 3. Semantic AI Auditor Check
        is_ai_valid = ai_validate_scl_code(prompt, scl_code)

        success = is_struct_passed and is_dataflow_passed and is_ai_valid

        if success:
            if "Turns: 1" in result_output:
                pass_at_1 += 1
                pass_at_k += 1
                print(f" -> RESULT: PASS@1 (First-try success)")
            else:
                pass_at_k += 1
                print(f" -> RESULT: PASS@k (Succeed via RLEF multi-turn repair)")
        else:
            print(f" -> RESULT: FAILED")
            print(f"    - Structural Check Passed: {is_struct_passed}")
            print(f"    - Data-Flow Check Passed: {is_dataflow_passed}")
            print(f"    - AI Auditor Approved: {is_ai_valid}")

    print(f"\n==========================================")
    print(f"BENCHMARK SUMMARY")
    print(f"Total Tests: {total_tests}")
    print(f"Pass@1 (First Try): {pass_at_1}/{total_tests} ({pass_at_1/total_tests*100:.1f}%)")
    print(f"Pass@k (With RLEF): {pass_at_k}/{total_tests} ({pass_at_k/total_tests*100:.1f}%)")
    print(f"==========================================\n")

if __name__ == "__main__":
    run_evaluation()