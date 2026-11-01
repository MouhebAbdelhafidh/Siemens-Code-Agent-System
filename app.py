import os
import sys
import streamlit as st

# Add project root to path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from src.industrial_server import generate_scl_with_rag, validate_scl_structure, validate_scl_data_flow_paths
from src.infrastructure.simaticml_builder import generate_simaticml_for_fb

st.set_page_config(
    page_title="Industrial SCL Agent & SimaticML Studio",
    page_icon="⚙️",
    layout="wide"
)

st.title("⚙️ Industrial SCL Agent & SimaticML Studio")
st.markdown("Automated Siemens SCL code generation, IEC 61131-3 static validation, RLEF self-repair, and TIA Portal SimaticML XML export.")

# Sidebar configuration
st.sidebar.header("Agent Configuration")
model_name = st.sidebar.selectbox("Coding Model", ["qwen2.5-coder:7b"], index=0)
plc_target = st.sidebar.selectbox("PLC Family", ["S7-1500", "S7-1200", "S7-400"], index=0)
block_name_input = st.sidebar.text_input("Default Function Block Name", value="FB_SafetyInterlock")

# Main Interface
prompt_text = st.text_area(
    "Enter Industrial Automation Requirement (Natural Language):",
    value="Write a Siemens SCL Function Block named FB_ConveyorSafety with an E-Stop NC input, reset button, and fault latching.",
    height=100
)

col1, col2 = st.columns([1, 1])

if st.button("🚀 Generate & Validate SCL Code", type="primary"):
    if not prompt_text.strip():
        st.warning("Please enter a valid automation prompt.")
    else:
        with st.spinner("Drafting SCL via local Qwen RAG pipeline & running RLEF validation..."):
            # Execute generation
            raw_output = generate_scl_with_rag(prompt_text)
            
            # Extract code clean
            scl_code = raw_output
            if "```scl" in raw_output:
                parts = raw_output.split("```scl")
                if len(parts) > 1:
                    scl_code = parts[1].split("```")[0].strip()
            elif "```" in raw_output:
                parts = raw_output.split("```")
                if len(parts) > 1:
                    code_block = parts[1].strip()
                    if code_block.startswith("scl"):
                        code_block = code_block[3:].strip()
                    scl_code = code_block.split("```")[0].strip()

            st.session_state["scl_code"] = scl_code
            st.session_state["raw_output"] = raw_output

        st.success("Generation and validation cycle completed!")

# Display results if available in session state
if "scl_code" in st.session_state:
    st.markdown("---")
    tab1, tab2, tab3 = st.tabs(["📝 Generated SCL Code", "🔍 Validation & RLEF Trace", "📦 SimaticML XML Export"])

    with tab1:
        st.subheader("Siemens Structured Control Language (SCL)")
        st.code(st.session_state["scl_code"], language="pascal")

    with tab2:
        st.subheader("Static Analysis & Compliance Audit")
        scl = st.session_state["scl_code"]
        
        struct_res = validate_scl_structure(scl)
        dataflow_res = validate_scl_data_flow_paths(scl)
        
        st.write("**Structural Check:**")
        st.info(struct_res)
        
        st.write("**Data-Flow Check:**")
        st.info(dataflow_res)
        
        with st.expander("View Full Raw Execution Log"):
            st.text(st.session_state["raw_output"])

    with tab3:
        st.subheader("TIA Portal Openness SimaticML Serialization")
        block_name = st.text_input("SimaticML Block Name", value=block_name_input)
        
        if st.button("Generate SimaticML XML"):
            xml_data = generate_simaticml_for_fb(block_name, st.session_state["scl_code"])
            st.session_state["xml_data"] = xml_data
            st.success("SimaticML XML generated successfully!")

        if "xml_data" in st.session_state:
            st.text_area("SimaticML XML Output (Schema v4)", value=st.session_state["xml_data"], height=300)
            st.download_button(
                label="📥 Download SimaticML XML (.xml)",
                data=st.session_state["xml_data"],
                file_name=f"{block_name}.xml",
                mime="application/xml"
            )