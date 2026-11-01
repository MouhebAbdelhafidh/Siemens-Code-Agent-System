import os
import json
import pytest
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.industrial_server import (
    generate_scl_with_rag,
    validate_scl_structure,
    validate_scl_data_flow_paths,
    fingerprint_block
)
from src.validators.plcopen_validator import validate_scl_structure
from src.validators.scl_dataflow_analyzer import validate_scl_data_flow_paths

# Define a benchmark suite of industrial test vectors and their safety invariants
BENCHMARK_SUITE = [
    {
        "id": "test_conveyor_safety",
        "prompt": "Write a Siemens SCL FB for an emergency stop conveyor circuit with NC safety contacts, fault latching, and R_TRIG reset.",
        "expected_no_faults": True,
        "must_contain": ["FUNCTION_BLOCK", "BEGIN", "END_FUNCTION_BLOCK", "R_TRIG"]
    },
    {
        "id": "test_pid_temperature_loop",
        "prompt": "Write a Siemens SCL block for a temperature control loop using CONT_C with high/low limit alarms and anti-windup.",
        "expected_no_faults": True,
        "must_contain": ["FUNCTION_BLOCK", "CONT_C"]
    }
]

@pytest.mark.parametrize("test_case", BENCHMARK_SUITE, ids=lambda x: x["id"])
def test_industrial_generation_pipeline(test_case):
    """Executes end-to-end regression testing on agent-generated SCL blocks."""
    prompt = test_case["prompt"]
    
    print(f"\n[Regression Test] Running benchmark: {test_case['id']}")
    
    # 1. Execute generation and multi-agent audit loop
    generation_result = generate_scl_with_rag(prompt)
    assert "CRITIQUE PASSED" in generation_result or "Multi-Agent Audit Status" in generation_result, \
        f"Failure: Agent audit rejected generation for {test_case['id']}"
        
    # Extract SCL code block from markdown output
    code_lines = generation_result.split("```scl")
    assert len(code_lines) > 1, "Failure: Failed to extract SCL code block from response."
    scl_code = code_lines[1].split("```")[0].strip()
    
    # 2. Run structural validation audit
    struct_report = validate_scl_structure(scl_code)
    assert "AUDIT SUCCESS" in struct_report, f"Structural Validation Failed:\n{struct_report}"
    
    # 3. Run data flow and control flow analysis
    dataflow_report = validate_scl_data_flow_paths(scl_code)
    assert "DATA FLOW ANALYSIS SUCCESS" in dataflow_report, f"Data Flow Audit Failed:\n{dataflow_report}"
    
    # 4. Verify mandatory syntax tokens are present
    for token in test_case["must_contain"]:
        assert token in scl_code, f"Mandatory architectural token '{token}' missing from generated block."
        
    # 5. Generate and log cryptographic content-addressed fingerprint
    fingerprint = fingerprint_block(scl_code)
    print(f"[Regression Test] PASSED. Content Fingerprint: {fingerprint}")