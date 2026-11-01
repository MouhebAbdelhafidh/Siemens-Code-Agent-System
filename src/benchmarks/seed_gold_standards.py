import os
import sys

# Ensure project root is in PYTHONPATH
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.industrial_server import ingest_gold_standard_template

def seed_database():
    print("[Seeding] Ingesting gold-standard SCL templates into ChromaDB...")

    # 1. Conveyor Safety Interlock Template
    ingest_gold_standard_template(
        title="FB_ConveyorSafety",
        description="Standard Siemens SCL FB with NC safety contacts, fault latching, and R_TRIG reset.",
        scl_code="""
FUNCTION_BLOCK FB_ConveyorSafety
VAR_INPUT
    bEStop_NC : BOOL := TRUE;
    bResetCmd : BOOL := FALSE;
    bEnable : BOOL := FALSE;
    bConveyorCmd : BOOL := FALSE;
END_VAR
VAR_OUTPUT
    bMotorRun : BOOL := FALSE;
    bFaultOut : BOOL := FALSE;
END_VAR
VAR
    bFaultLatched : BOOL := FALSE;
    rTrig_Reset : R_TRIG;
END_VAR
BEGIN
    IF NOT bEStop_NC THEN
        bFaultLatched := TRUE;
    END_IF;
    
    rTrig_Reset(CLK := bResetCmd);
    IF rTrig_Reset.Q AND bEStop_NC THEN
        bFaultLatched := FALSE;
    END_IF;
    
    bFaultOut := bFaultLatched;
    bMotorRun := bEnable AND bConveyorCmd AND NOT bFaultLatched AND bEStop_NC;
END_FUNCTION_BLOCK
"""
    )

    # 2. Hydraulic Press Thermal Overload Template
    ingest_gold_standard_template(
        title="FB_HydraulicPress",
        description="Hydraulic press control block with thermal overload monitoring and edge-triggered reset.",
        scl_code="""
FUNCTION_BLOCK FB_HydraulicPress
VAR_INPUT
    bThermal_NC : BOOL := TRUE;
    bResetCmd : BOOL := FALSE;
END_VAR
VAR_OUTPUT
    bFaultOut : BOOL := FALSE;
END_VAR
VAR
    bFaultLatched : BOOL := FALSE;
    rTrig_Reset : R_TRIG;
END_VAR
BEGIN
    IF NOT bThermal_NC THEN
        bFaultLatched := TRUE;
    END_IF;
    
    rTrig_Reset(CLK := bResetCmd);
    IF rTrig_Reset.Q AND bThermal_NC THEN
        bFaultLatched := FALSE;
    END_IF;
    
    bFaultOut := bFaultLatched;
END_FUNCTION_BLOCK
"""
    )
# 3. Sensor Scanner Array Iteration Template
    ingest_gold_standard_template(
        title="FB_SensorScanner",
        description="Siemens SCL Function Block utilizing a FOR loop to scan an array of sensors.",
        scl_code="""
FUNCTION_BLOCK FB_SensorScanner
VAR
    aSensors : ARRAY[1..16] OF BOOL;
END_VAR
VAR_OUTPUT
    nActiveCount : INT := 0;
END_VAR
VAR_TEMP
    i : INT;
END_VAR
BEGIN
    nActiveCount := 0;
    FOR i := 1 TO 16 DO
        IF aSensors[i] THEN
            nActiveCount := nActiveCount + 1;
        END_IF;
    END_FOR;
END_FUNCTION_BLOCK
"""
    )
    print("[Seeding] Gold standards successfully ingested into ChromaDB!")

if __name__ == "__main__":
    seed_database()