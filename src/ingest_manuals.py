import os
from chromadb import PersistentClient
from sentence_transformers import SentenceTransformer
from pypdf import PdfReader

# 1. Initialize local persistent vector store
client = PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection(name="siemens_scl_manuals")

# 2. Load a lightweight, high-performance local embedding model
# Runs completely offline on your local hardware
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

def ingest_pdf(file_path: str):
    print(f"Processing {file_path}...")
    reader = PdfReader(file_path)
    
    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        if not text.strip():
            continue
            
        # Create a unique ID for the chunk
        chunk_id = f"{os.path.basename(file_path)}_page_{i}"
        
        # Generate local embedding vector
        vector = embedding_model.encode(text).tolist()
        
        # Store in ChromaDB
        collection.add(
            ids=[chunk_id],
            embeddings=[vector],
            documents=[text],
            metadatas=[{"source": file_path, "page": i}]
        )
    print(f"Successfully ingested {file_path} into local vector store.")

# Example usage:
ingest_pdf("knowledge_base/STEP_7_WinCC_V16_enUS_en-US.pdf")
ingest_pdf("knowledge_base/109750255_Programming-Guideline-Safety_DOC_V1_6_en.pdf")