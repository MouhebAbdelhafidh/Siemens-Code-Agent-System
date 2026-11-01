import os
import xml.etree.ElementTree as ET

def generate_simaticml_for_fb(block_name: str, scl_code: str) -> str:
    """
    Wraps generated SCL code into a TIA Portal Openness compliant SimaticML XML document
    for direct software block import (`SW.Blocks.FB`).
    """
    # Define standard Siemens SimaticML namespaces
    root = ET.Element("Document")
    root.set("xmlns", "http://www.siemens.com/automation/Openness/SW/Document/v4")
    
    engineering = ET.SubElement(root, "Engineering")
    engineering.set("version", "V19")
    
    sw_block = ET.SubElement(root, "SW.Blocks.FB")
    sw_block.set("ID", "0")
    
    object_List = ET.SubElement(sw_block, "ObjectList")
    
    # Attribute list for block properties
    attribute_list = ET.SubElement(sw_block, "AttributeList")
    
    name_elem = ET.SubElement(attribute_list, "Name")
    name_elem.text = block_name
    
    header_version = ET.SubElement(attribute_list, "HeaderVersion")
    header_version.text = "0.1"

    # Programming Language specifier (SCL)
    programming_language = ET.SubElement(attribute_list, "ProgrammingLanguage")
    programming_language.text = "SCL"

    # CompileUnit wrapping the raw SCL source inside CDATA
    compile_unit = ET.SubElement(sw_block, "CompileUnit")
    compile_unit.set("ID", "1")
    compile_unit.set("CompositionName", "CompileUnits")
    
    cu_attr = ET.SubElement(compile_unit, "AttributeList")
    
    # SCL Source code wrapped in CDATA
    source_code = ET.SubElement(compile_unit, "SourceCode")
    source_code.text = f"<![CDATA[\n{scl_code.strip()}\n]]>"

    # Pretty print XML string
    rough_string = ET.tostring(root, encoding="utf-8")
    
    # Clean up XML declaration and namespace artifacts for raw Siemens import compatibility
    xml_header = '<?xml version="1.0" encoding="utf-8"?>\n'
    formatted_xml = xml_header + rough_string.decode("utf-8").replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    
    return formatted_xml


def parse_simaticml_to_scl(xml_file_path: str) -> str:
    """
    Parses an exported TIA Portal SimaticML XML block file and extracts the embedded SCL source code.
    """
    if not os.path.exists(xml_file_path):
        return f"SIMATICML ERROR: XML file not found at {xml_file_path}"

    try:
        tree = ET.parse(xml_file_path)
        root = tree.getroot()
        
        # Search for SourceCode nodes across namespaces
        for elem in root.iter():
            if elem.tag.endswith("SourceCode") and elem.text:
                return elem.text.strip()
                
        return "SIMATICML WARNING: No SourceCode node found in XML document."
    except Exception as e:
        return f"SIMATICML PARSING EXCEPTION: {str(e)}"