import os
from fpdf import FPDF

def create_pdf(output_path):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=15)
    pdf.cell(200, 10, txt="NeuroFlow Architecture Guide", ln=1, align='C')
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 10, "The main topic of this document is the NeuroFlow RAG Architecture. "
                          "NeuroFlow uses advanced dense and sparse retrieval techniques along with reranking "
                          "to provide the highest quality semantic search. The system is designed to handle "
                          "millions of documents securely.")
    pdf.output(output_path)
    print(f"Created {output_path}")

if __name__ == "__main__":
    create_pdf("tests/fixtures/test_doc.pdf")
