import sys
import json
import asyncio

def run():
    if len(sys.argv) < 3:
        print("Usage: python -m pipelines.ingestion.sandbox_extractor <file_path> <source_type>")
        sys.exit(1)
        
    file_path = sys.argv[1]
    source_type = sys.argv[2]
    
    pages = []
    try:
        if source_type == "pdf":
            from pipelines.ingestion.extractors.pdf_extractor import extract_pdf
            pages = extract_pdf(file_path)
        elif source_type == "docx":
            from pipelines.ingestion.extractors.docx_extractor import extract_docx
            pages = extract_docx(file_path)
        elif source_type == "csv":
            from pipelines.ingestion.extractors.csv_extractor import extract_csv
            pages = extract_csv(file_path)
        elif source_type == "text":
            from pipelines.ingestion.extractors.base import ExtractedPage
            with open(file_path, "r", encoding="utf-8") as f:
                pages = [ExtractedPage(page_number=1, content=f.read(), content_type="text", metadata={})]
        else:
            # We don't support network-dependent extraction in the sandbox
            raise ValueError(f"Unsupported sandboxed source type: {source_type}")
            
        output = []
        for p in pages:
            output.append({
                "page_number": p.page_number,
                "content": p.content,
                "content_type": p.content_type,
                "metadata": p.metadata
            })
            
        print(json.dumps(output))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

if __name__ == "__main__":
    run()
