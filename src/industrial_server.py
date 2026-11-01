import hashlib
import json
import os
import re
from chromadb import PersistentClient
from fastmcp import FastMCP
import ollama
from sentence_transformers import SentenceTransformer

from src.infrastructure.rlaif_logger import log_preference_pair
from src.infrastructure.plcsim_harness import run_plcsim_simulation_harness
from src.validators.plcopen_validator import validate_plcopen_semantic
from src.validators.scl_dataflow_analyzer import validate_scl_data_flow_paths
from src.infrastructure.tia_openness_bridge import compile_scl_via_tia_openness
from src.infrastructure.audit_ledger import record_audit_event
from src.validators.plcopen_validator import validate_scl_structure
from src.validators.scl_dataflow_analyzer import analyze_scl_data_flow
from src.infrastructure.simaticml_builder import generate_simaticml_for_fb, parse_simaticml_to_scl

# Initialize the industrial MCP server
mcp = FastMCP("Industrial SCL Code Agent")

# Absolute path configuration for air-gapped consistency
BASE_DIR = r"C:\Users\mouhe\Desktop\industrial-mcp-agent"
client = PersistentClient(path=os.path.join(BASE_DIR, "chroma_db"))
collection = client.get_or_create_collection(name="siemens_scl_manuals")
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")


def fingerprint_block(scl_code: str) -> str:
    """Generates a 12-character content-addressed SHA-256 fingerprint for SCL blocks."""
    # Normalize line endings to ensure consistent cross-platform hashing
    normalized_code = scl_code.replace("\r\n", "\n").strip()
    return hashlib.sha256(normalized_code.encode("utf-8")).hexdigest()[:12]

@mcp.tool()
def export_scl_to_simaticml(block_name: str, scl_code: str, output_xml_path: str = "block_export.xml") -> str:
    """
    Converts raw Siemens SCL code into a TIA Portal Openness compliant SimaticML XML file
    ready for automated import into S7-1200 / S7-1500 projects.
    """
    # Sanitize path: if Claude passes a Linux path or root path, redirect to a local outputs folder
    if "/" in output_xml_path or "\\" in output_xml_path:
        filename = os.path.basename(output_xml_path)
    else:
        filename = output_xml_path or f"{block_name}.xml"
        
    local_output_dir = os.path.join(os.path.dirname(__file__), "..", "outputs")
    os.makedirs(local_output_dir, exist_ok=True)
    
    final_path = os.path.join(local_output_dir, filename)

    try:
        xml_content = generate_simaticml_for_fb(block_name, scl_code)
        with open(final_path, "w", encoding="utf-8") as f:
            f.write(xml_content)
            
        return (
            f"SIMATICML EXPORT SUCCESS:\n"
            f"- Block Name: {block_name}\n"
            f"- Output File: {os.path.abspath(final_path)}\n"
            f"- Format: TIA Portal Openness XML Schema v4"
        )
    except Exception as e:
        return f"SIMATICML EXPORT FAILED: {str(e)}"

@mcp.tool()
def ingest_gold_standard_template(
    title: str, description: str, scl_code: str
) -> str:
    """Ingests a human-verified, production-grade SCL block into local ChromaDB with content fingerprinting."""
    fingerprint = fingerprint_block(scl_code)
    doc_text = (
        f"TITLE: {title}\nDESCRIPTION: {description}\nFINGERPRINT: {fingerprint}\n"
        f"VERIFIED SCL CODE:\n{scl_code}"
    )
    vector = embedding_model.encode(doc_text).tolist()
    chunk_id = f"gold_template_{title.lower().replace(' ', '_')}_{fingerprint}"

    collection.add(
        ids=[chunk_id],
        embeddings=[vector],
        documents=[doc_text],
        metadatas=[{
            "type": "gold_standard", 
            "title": title, 
            "fingerprint": fingerprint
        }],
    )
    return f"SUCCESS: Gold-standard template '{title}' added to ChromaDB with fingerprint [{fingerprint}]."

def clean_scl_output(raw_text: str) -> str:
    """Robustly extracts SCL code between FUNCTION_BLOCK and END_FUNCTION_BLOCK using regex."""
    text = raw_text.strip()
    
    # Use regex to find FUNCTION_BLOCK ... END_FUNCTION_BLOCK (case-insensitive)
    match = re.search(r'(FUNCTION_BLOCK\s+[\w]+\s+[\s\S]*?END_FUNCTION_BLOCK)', text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
        
    # Fallback substring search
    start = text.upper().find("FUNCTION_BLOCK")
    end = text.upper().find("END_FUNCTION_BLOCK")
    if start != -1:
        if end != -1:
            return text[start:end + len("END_FUNCTION_BLOCK")].strip()
        return text[start:].strip()
        
    return text


@mcp.tool()
def generate_scl_with_rag(prompt: str) -> str:
    """
    MANDATORY TOOL: Execution-Grounded Multi-Turn SCL Generation Loop (RLEF pattern).
    Uses deterministic static validators as execution feedback to iteratively 
    repair code, computes SHA-256 block fingerprint, and logs multi-turn RLAIF trajectories for DPO.
    """
    # 1. Retrieve relevant reference context from ChromaDB
    query_vector = embedding_model.encode(prompt).tolist()
    retrieval_results = collection.query(
        query_embeddings=[query_vector], n_results=2
    )
    retrieved_docs = retrieval_results.get("documents", [[]])[0]

    context_text = (
        "\n---\n".join(retrieved_docs)
        if retrieved_docs
        else "No specific manual or template excerpts found."
    )

    # System guardrails shared across agents
    guardrails_text = (
        "MANDATORY ARCHITECTURAL RULES:\n"
        "1. HARDWARE POLARITY (NC Contacts): Physical Stop/Overload/Limit "
        "signals are Normally Closed (NC). Healthy = TRUE. Tripped/Wire-break = FALSE.\n"
        "2. NO METHOD BLOCKS: Do NOT use METHOD ... END_METHOD inside an FB. "
        "All logic lives in BEGIN ... END_FUNCTION_BLOCK.\n"
        "3. CONSTANTS & TIMERS: Define states in VAR CONSTANT. Pass timers via "
        "VAR_IN_OUT or unique VAR instances. Never zero out or re-initialize timers incorrectly.\n"
        "4. FAULT LATCHING & RESETS: Faults MUST latch (Fault := TRUE) until "
        "cleared via a rising-edge reset (R_TRIG).\n"
        "5. ARRAY ASSIGNMENTS: Use explicit FOR loops, never scalar assignment to arrays.\n"
        "6. FEEDBACK SUPERVISION: Startup timers must time out if feedback is "
        "missing after a start command.\n"
        "7. FORCED INTERLOCKS: Outputs must be forced FALSE in fault states or if enables drop."
    )

    # --- STEP 2: GENERATOR AGENT INITIAL DRAFT ---
    generator_system = (
        "You are a Senior Siemens Automation Engineer writing strict SCL for TIA Portal.\n"
        "CRITICAL INSTRUCTION: Output ONLY valid Siemens Structured Control Language (SCL) code. "
        "Do NOT include conversational preambles, explanations, or text outside of the code block. "
        "Start your response directly with FUNCTION_BLOCK and end with END_FUNCTION_BLOCK.\n"
        "When specific variable names (e.g., bEStop_NC, bFaultLatched) are requested in the prompt, "
        "you MUST use those exact identifiers.\n\n"
        f"--- RETRIEVED REFERENCE CONTEXT ---\n{context_text}\n-----------------------------------\n\n"
        f"{guardrails_text}"
    )

    print("[RLEF Agent] Generator is drafting initial SCL code...")
    messages = [
        {"role": "system", "content": generator_system},
        {"role": "user", "content": prompt},
    ]
    gen_response = ollama.chat(
        model="qwen2.5-coder:7b",
        messages=messages,
    )
    initial_raw = gen_response["message"]["content"]
    initial_draft = clean_scl_output(initial_raw)
    draft_code = initial_draft

    # --- STEP 3: RLEF EXECUTION-GROUNDED REFINEMENT LOOP ---
    max_turns = 3
    turn = 0
    validation_passed = False
    trajectory = []

    while turn < max_turns and not validation_passed:
        turn += 1
        print(f"[RLEF Agent] Execution Feedback Turn {turn}/{max_turns}: Running structural & data-flow validators...")

        # Run deterministic static analyzers as our industrial "execution feedback"
        struct_report = validate_scl_structure(draft_code)
        dataflow_report = validate_scl_data_flow_paths(draft_code)

        has_structural_error = "AUDIT FAILED" in struct_report or "Fatal" in struct_report
        has_dataflow_error = "FAILED" in dataflow_report

        if not has_structural_error and not has_dataflow_error:
            validation_passed = True
            print("[RLEF Agent] Execution feedback indicates all static checks passed!")
            break

        # Construct execution feedback observation
        feedback_content = (
            f"Your previous SCL draft failed deterministic industrial validation checks.\n\n"
            f"STRUCTURAL AUDIT REPORT:\n{struct_report}\n\n"
            f"DATA FLOW ANALYSIS REPORT:\n{dataflow_report}\n\n"
            f"Please rewrite the SCL block to strictly resolve these exact errors while adhering to all architectural rules. Output ONLY valid SCL code."
        )

        trajectory.append({
            "turn": turn,
            "code": draft_code,
            "structural_report": struct_report,
            "dataflow_report": dataflow_report
        })

        messages.append({"role": "assistant", "content": draft_code})
        messages.append({"role": "user", "content": feedback_content})

        print(f"[RLEF Agent] Refining SCL code based on execution feedback...")
        refine_response = ollama.chat(
            model="qwen2.5-coder:7b",
            messages=messages,
        )
        draft_code = clean_scl_output(refine_response["message"]["content"])

    # --- STEP 4: RLAIF PREFERENCE LOGGING WITH TRAJECTORY ---
    if turn > 1 and validation_passed:
        log_preference_pair(
            prompt=prompt,
            rejected_code=initial_draft,
            chosen_code=draft_code,
            feedback_trajectory=trajectory
        )

    # Compute deterministic fingerprint for version tracking
    block_fingerprint = fingerprint_block(draft_code)
    status_msg = "SUCCESS (Validated)" if validation_passed else "WARNING (Max turns reached)"

    return (
        f"### RLEF Execution-Grounded Status: {status_msg} (Turns: {turn})\n"
        f"### Content-Addressed Fingerprint: `{block_fingerprint}`\n\n"
        f"```scl\n{draft_code}\n```"
    )

@mcp.tool()
def validate_scl_structure(scl_code: str) -> str:
    """Performs strict pre-compilation structural audits on SCL code."""
    errors = []
    warnings = []

    if not scl_code.strip():
        return "AUDIT FAILED: Generated SCL code is empty."

    if "FUNCTION_BLOCK" not in scl_code:
        errors.append("Fatal: Missing 'FUNCTION_BLOCK' declaration.")
    if "END_FUNCTION_BLOCK" not in scl_code:
        errors.append("Fatal: Missing 'END_FUNCTION_BLOCK' termination statement.")
    if "BEGIN" not in scl_code:
        errors.append("Fatal: Missing 'BEGIN' execution block marker.")
    if "METHOD" in scl_code or "END_METHOD" in scl_code:
        errors.append("Fatal: 'METHOD' blocks detected. S7-1200/1500 FB logic must reside directly inside BEGIN ... END_FUNCTION_BLOCK.")

    if errors:
        return "AUDIT FAILED:\n" + "\n".join(errors)

    return "AUDIT SUCCESS: Structural SCL compliance checks passed."


@mcp.tool()
def validate_plcopen_semantic(scl_code: str, xml_spec_path: str) -> str:
    """Performs semantic interface validation by cross-checking generated SCL code against PLCopen XML specification."""
    return validate_semantic_interface(scl_code, xml_spec_path)


@mcp.tool()
def validate_scl_data_flow_paths(scl_code: str) -> str:
    """Performs advanced data flow and control flow analysis to detect unlatched faults and dead code paths."""
    return analyze_scl_data_flow(scl_code)

@mcp.tool()
def compile_scl_in_tia_portal(scl_code: str, tia_project_path: str, plc_name: str = "PLC_1") -> str:
    """
    Saves generated SCL code to an external source file and triggers a native TIA Portal 
    Openness compilation check against a real Siemens project workspace.
    """
    # Save code to a temporary SCL source file in workspace
    scl_file_path = os.path.join(BASE_DIR, "temp_generated_block.scl")
    with open(scl_file_path, "w", encoding="utf-8") as f:
        f.write(scl_code)
        
    return compile_scl_via_tia_openness(scl_file_path, tia_project_path, plc_name)

@mcp.tool()
def dry_run_code_in_plcsim(instance_name: str, test_vectors_json: str) -> str:
    """Automated pre-review dry-run harness using Siemens PLCSIM Advanced API."""
    try:
        test_inputs = json.loads(test_vectors_json) if test_vectors_json else {}
    except Exception:
        test_inputs = {}
        
    return run_plcsim_simulation_harness(instance_name, test_inputs)


if __name__ == "__main__":
    mcp.run()