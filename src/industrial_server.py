import hashlib
import json
import os
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


@mcp.tool()
def generate_scl_with_rag(prompt: str) -> str:
    """
    MANDATORY TOOL: Uses a Multi-Agent Critic-Generator loop to write, audit,
    and self-correct Siemens SCL code locally via Ollama. Computes deterministic 
    SHA-256 block fingerprint and logs RLAIF preference pairs for DPO training.
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
        "1. HARDWARE POLARITY (NC Contacts): Physical Stop/Overload/Limit"
        " signals are Normally Closed (NC). Healthy = TRUE. Tripped/Wire-break ="
        " FALSE.\n"
        "2. NO METHOD BLOCKS: Do NOT use METHOD ... END_METHOD inside an FB."
        " All logic lives in BEGIN ... END_FUNCTION_BLOCK.\n"
        "3. CONSTANTS & TIMERS: Define states in VAR CONSTANT. Pass timers via"
        " VAR_IN_OUT or unique VAR instances. Never zero out or re-initialize"
        " timers incorrectly.\n"
        "4. FAULT LATCHING & RESETS: Faults MUST latch (Fault := TRUE) until"
        " cleared via a rising-edge reset (R_TRIG).\n"
        "5. ARRAY ASSIGNMENTS: Use explicit FOR loops, never scalar assignment"
        " to arrays.\n"
        "6. FEEDBACK SUPERVISION: Startup timers must time out if feedback is"
        " missing after a start command.\n"
        "7. FORCED INTERLOCKS: Outputs must be forced FALSE in fault states or"
        " if enables drop."
    )

    # --- STEP 2: GENERATOR AGENT ---
    generator_system = (
        "You are a Senior Siemens Automation Engineer writing strict SCL for TIA"
        " Portal (S7-1200/S7-1500).\n"
        f"--- RETRIEVED REFERENCE CONTEXT ---\n{context_text}\n-----------------------------------\n\n"
        f"{guardrails_text}"
    )

    print("[Agent Loop] Generator is drafting initial SCL code...")
    gen_response = ollama.chat(
        model="qwen2.5-coder:7b",
        messages=[
            {"role": "system", "content": generator_system},
            {"role": "user", "content": prompt},
        ],
    )
    initial_draft = gen_response["message"]["content"]
    draft_code = initial_draft

    # --- STEP 3: SAFETY CRITIC AGENT ---
    critic_system = (
        "You are a rigorous Industrial Safety & PLC Code Auditor. Your job is to"
        " review generated Siemens SCL code against strict industrial safety"
        " standards.\n"
        f"{guardrails_text}\n\n"
        "Analyze the provided SCL code. If it violates any rule (e.g., treating"
        " NC inputs as active-high, missing timer instances, unlatched faults,"
        " or illegal syntax), output a detailed critique starting with 'CRITIQUE"
        " FAILED:' followed by the exact fixes needed.\n"
        "If the code is fully compliant and safe, output exactly 'CRITIQUE PASSED'."
    )

    print("[Agent Loop] Safety Critic is auditing the draft...")
    critic_response = ollama.chat(
        model="qwen2.5-coder:7b",
        messages=[
            {"role": "system", "content": critic_system},
            {
                "role": "user",
                "content": (
                    f"Audit this generated SCL code for prompt: '{prompt}'\n\nCode"
                    f" to audit:\n{draft_code}"
                ),
            },
        ],
    )
    critic_feedback = critic_response["message"]["content"]

    # --- STEP 4: REFINEMENT LOOP (If critic fails) ---
    max_retries = 1
    attempt = 0
    refinement_occurred = False

    while "CRITIQUE FAILED" in critic_feedback and attempt < max_retries:
        attempt += 1
        refinement_occurred = True
        print(
            f"[Agent Loop] Critic found issues. Refinement pass {attempt}/{max_retries}..."
        )

        refine_system = (
            "You are a Senior Siemens Automation Engineer. Your previous draft"
            " failed a safety and logic audit. Fix the code according to the"
            " Critic's feedback while maintaining all mandatory architectural"
            " rules.\n\nCRITIC FEEDBACK:\n"
            f"{critic_feedback}"
        )

        refine_response = ollama.chat(
            model="qwen2.5-coder:7b",
            messages=[
                {"role": "system", "content": refine_system},
                {
                    "role": "user",
                    "content": (
                        f"Rewrite the SCL block fixing all critique points.\nPrevious"
                        f" Code:\n{draft_code}"
                    ),
                },
            ],
        )
        draft_code = refine_response["message"]["content"]

        # Re-audit
        critic_response = ollama.chat(
            model="qwen2.5-coder:7b",
            messages=[
                {"role": "system", "content": critic_system},
                {
                    "role": "user",
                    "content": f"Re-audit this corrected SCL code:\n{draft_code}",
                },
            ],
        )
        critic_feedback = critic_response["message"]["content"]

    # --- STEP 5: RLAIF PREFERENCE LOGGING ---
    if refinement_occurred and "CRITIQUE PASSED" in critic_feedback:
        log_preference_pair(
            prompt=prompt, rejected_code=initial_draft, chosen_code=draft_code
        )

    # Compute deterministic fingerprint for version tracking and regression audits
    block_fingerprint = fingerprint_block(draft_code)

    return (
        f"### Multi-Agent Audit Status: {critic_feedback.splitlines()[0]}\n"
        f"### Content-Addressed Fingerprint: `{block_fingerprint}`\n\n"
        f"```scl\n{draft_code}\n```"
    )


@mcp.tool()
def validate_scl_structure(scl_code: str) -> str:
    """Performs pre-compilation structural audits on SCL code."""
    errors = []
    warnings = []

    if "FUNCTION_BLOCK" in scl_code and "END_FUNCTION_BLOCK" not in scl_code:
        errors.append("Fatal: Missing 'END_FUNCTION_BLOCK' termination statement.")
    if "BEGIN" not in scl_code:
        errors.append("Fatal: Missing 'BEGIN' execution block marker.")
    if "METHOD" in scl_code or "END_METHOD" in scl_code:
        errors.append(
            "Fatal: 'METHOD' blocks detected. S7-1200/1500 FB logic must reside"
            " directly inside BEGIN ... END_FUNCTION_BLOCK."
        )

    report = []
    if errors:
        report.append("AUDIT FAILED:\n- " + "\n- ".join(errors))
    if warnings:
        report.append("AUDIT WARNINGS:\n- " + "\n- ".join(warnings))

    if not errors and not warnings:
        return "AUDIT SUCCESS: Structural SCL compliance checks passed."

    return "\n".join(report)


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