# ⚙️ Industrial SCL Agent & SimaticML Studio

An air-gapped, production-grade agentic pipeline designed to generate, statically validate, self-repair, and export **Siemens TIA Portal SCL (Structured Control Language)** code. Powered by **FastMCP**, local LLMs (**Qwen2.5-Coder:7b** via Ollama), **ChromaDB** retrieval-augmented generation (RAG), and deterministic **IEC 61131-3** compliance validators.

---

## 🏗️ System Architecture & Multi-Agent Pipeline
<img width="530" height="700" alt="image" src="https://github.com/user-attachments/assets/5d75a4dd-2636-42c8-9647-5b97567dfd39" />

</br>

##  🏗️ Agentic and Core loops 

</br>

###  Generator Agent (qwen2.5-coder:7b)

Synthesizes IEC 61131-3 compliant Function Blocks (FB) from natural language engineering specs.

Enforces strict hardware polarity rules (Normally Closed E-Stop contacts, fail-safe fault latching, and R_TRIG edge detection).

### RLEF Execution-Grounded Self-Repair Loop

Instead of blind generation, agent outputs are passed directly through deterministic static analyzers acting as execution feedback.

If structural errors (missing BEGIN, invalid block headers) or data-flow anomalies (unlatched faults) are detected, audit reports are injected back into the conversation trajectory.

The model iteratively repairs the code across multi-turn trajectories (up to 3 turns) before returning a verified block.

### RLAIF & DPO Trajectory Logger

Captures multi-turn interaction histories where initial drafts failed and refined drafts succeeded.

Logs preference pairs (rejected_code vs chosen_code with feedback trajectories) into dpo_dataset.jsonl to support offline Direct Preference Optimization (DPO) fine-tuning via Hugging Face TRL.

### FastMCP & Claude Desktop Bridge

Exposes all core generation, validation, and XML export tools over the Model Context Protocol (MCP), enabling seamless execution directly inside AI clients like Claude Desktop.

## Project structure
industrial-mcp-agent/</br>
│</br>
├── app.py                      # Streamlit interactive web dashboard</br>
├── requirements.txt            # Locked project dependencies</br>
└── src/</br>
    ├── industrial_server.py    # FastMCP server exposing industrial tools & RLEF loop</br>
    ├── ingest_manuals.py       # ChromaDB vector ingestion pipeline for SCL manuals</br>
    ├── validators/</br>
    │   ├── plcopen_validator.py       # Structural SCL compliance checks</br>
    │   └── scl_dataflow_analyzer.py   # Data-flow and safety interlock audit</br>
    ├── infrastructure/</br>
    │   ├── simaticml_builder.py       # SimaticML XML schema v4 serializer</br>
    │   ├── rlaif_logger.py            # DPO preference pair trajectory logger</br>
    │   └── tia_openness_bridge.py     # TIA Portal Openness compiler bridge</br>
    └── benchmarks/                     # Golden test sets for SCL validation</br>
</br>
## Quick installation

### 1. Clone the Repository
git clone [https://github.com/your-username/industrial-mcp-agent.git](https://github.com/your-username/industrial-mcp-agent.git)
cd industrial-mcp-agent

### 2. Create & Activate Virtual Environment
python -m venv .venv
.venv\Scripts\Activate

### 3. Install Dependencies
pip install -r requirements.txt

### 4. Run the Streamlit Web Studio
streamlit run app.py

## TIA Portal Integration & Export

Validated SCL blocks can be serialized instantly into Siemens SimaticML XML Schema v4, allowing automation engineers to import code directly into Siemens TIA Portal S7-1200 / S7-1500 projects via TIA Portal Openness.
