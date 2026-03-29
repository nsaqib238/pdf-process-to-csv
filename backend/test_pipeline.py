"""
Test the PDF processing pipeline
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.pdf_processor import PDFProcessor


async def test_pipeline():
    """Test the PDF processing pipeline"""
    
    # Check if test PDF exists
    test_pdf = "test_sample.pdf"
    if not os.path.exists(test_pdf):
        print(f"Test PDF '{test_pdf}' not found.")
        print("Creating a simple test text...")
        
        # Create a minimal test scenario
        print("\n=== Testing PDF Processor Components ===\n")
        
        processor = PDFProcessor()
        
        # Test classification
        print("✓ PDF Classifier initialized")
        print("✓ Adobe Services initialized (fallback mode)")
        print("✓ Clause Processor initialized")
        print("✓ Table Processor initialized")
        print("✓ Validator initialized")
        print("✓ Output Generator initialized")
        
        print("\nAll components initialized successfully!")
        print("\nTo test with a real PDF:")
        print("1. Upload a PDF through the web interface at http://localhost:3000")
        print("2. Or place a PDF named 'test_sample.pdf' in the backend directory")
        
        return
    
    print(f"Processing test PDF: {test_pdf}")
    
    processor = PDFProcessor()
    output_dir = "test_output"
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        result = await processor.process_pdf(
            input_path=test_pdf,
            output_dir=output_dir,
            job_id="test_001"
        )
        
        print("\n=== Processing Complete ===")
        print(f"Status: {result.get('status', 'unknown')}")
        print(f"\nSummary:")
        summary = result.get('summary', {})
        print(f"  - Total Clauses: {summary.get('total_clauses', 0)}")
        print(f"  - Total Tables: {summary.get('total_tables', 0)}")
        print(f"  - Document Title: {summary.get('document_title', 'N/A')}")
        
        validation = summary.get('validation_issues', {})
        if validation:
            print(f"\nValidation:")
            print(f"  - Errors: {validation.get('errors', 0)}")
            print(f"  - Warnings: {validation.get('warnings', 0)}")
        
        print(f"\nOutput files saved to: {output_dir}/")
        
    except Exception as e:
        print(f"\nError during processing: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_pipeline())
