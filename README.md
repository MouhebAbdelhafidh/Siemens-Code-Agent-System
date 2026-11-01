# Industrial SCL Code Agent (industrial-mcp-agent)

An enterprise-ready, execution-grounded multi-agent engineering framework that bridges Large Language Models (LLMs) with industrial automation workflows (Siemens S7-1200/S7-1500 TIA Portal). Built using the Model Context Protocol (MCP) and local LLMs via Ollama, the system automates the generation, safety auditing, semantic verification, and compilation of Structured Control Language (SCL) blocks.

## Core Architectural Pillars

1. **Model Context Protocol (MCP) Server**: 
   - Exposes robust local tools (`generate_scl_with_rag`, structural validators, TIA compilation bridges) directly to reasoning clients like Claude Desktop.
2. **Execution-Grounded RLEF Loop**: 
   - Implements multi-turn Reinforcement Learning with Execution Feedback (inspired by meta-analysis on automated agentic repair). Instead of relying solely on soft LLM critics, generated SCL blocks are iteratively audited by hard, deterministic static analyzers and compiled against PLCopen rules.
3. **Industrial Safety Guardrails & Compliance**: 
   - Enforces strict safety rules including Normally Closed (NC) physical hardware polarity, fault latching with rising-edge `R_TRIG` resets, array boundary safety via explicit `FOR` loops, and prohibition of illegal `METHOD` blocks inside function blocks.
4. **Retrieval-Augmented Generation (RAG) & RLAIF**: 
   - Integrates a local ChromaDB vector store seeded with gold-standard Siemens templates and content-addressed SHA-256 block fingerprinting, paired with automated preference logging for DPO model alignment.
5. **Enterprise Integration Bridges**: 
   - Ready for TIA Portal Openness compilation checking and Siemens PLCSIM Advanced simulation harness dry-runs.
