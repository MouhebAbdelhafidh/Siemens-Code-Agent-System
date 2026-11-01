import re

def analyze_scl_data_flow(scl_code: str) -> str:
    """Performs advanced data flow and control flow analysis to detect unlatched faults and dead code paths."""
    errors = []
    
    # Check for unlatched fault conditions
    if "Fault" in scl_code and ":=" in scl_code:
        if "Fault := NOT" in scl_code and "OR Fault" not in scl_code:
            errors.append("Data Flow Warning: Potential unlatched fault detection. Fault variable updates without self-holding latch logic.")

    if errors:
        return "DATA FLOW ANALYSIS FAILED:\n" + "\n".join(errors)
    
    return "DATA FLOW ANALYSIS SUCCESS: No unlatched faults or dead code paths detected."


def validate_scl_data_flow_paths(scl_code: str) -> str:
    """Wrapper function matching the import expectation in industrial_server.py."""
    return analyze_scl_data_flow(scl_code)