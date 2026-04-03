#!/usr/bin/env python3
"""
Test Modal.com Integration with Table Extraction Pipeline

This script tests the integrated Modal+OpenAI fallback pipeline.
"""

import sys
import os
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from services.table_processor import TableProcessor
from config import settings


def test_modal_integration():
    """Test Modal.com integration with table processor."""
    
    print("\n" + "=" * 70)
    print("🧪 TESTING MODAL.COM INTEGRATION WITH TABLE PIPELINE")
    print("=" * 70)
    
    # Check configuration
    print("\n📋 Configuration:")
    print(f"   USE_MODAL_EXTRACTION: {settings.use_modal_extraction}")
    print(f"   MODAL_ENDPOINT: {settings.modal_endpoint[:60]}..." if settings.modal_endpoint else "   MODAL_ENDPOINT: Not configured")
    print(f"   MODAL_FALLBACK_MODE: {settings.modal_fallback_mode}")
    print(f"   MODAL_CONFIDENCE_THRESHOLD: {settings.modal_confidence_threshold}")
    print(f"   MODAL_TIMEOUT: {settings.modal_timeout}s")
    
    if not settings.use_modal_extraction:
        print("\n⚠️  Modal extraction is DISABLED in .env (USE_MODAL_EXTRACTION=false)")
        print("   The pipeline will use OpenAI/geometric extraction only.")
        return
    
    # Find test PDF
    test_pdf = Path("/home/runner/app/Tables AS3000 2018.pdf")
    if not test_pdf.exists():
        print(f"\n❌ Test PDF not found: {test_pdf}")
        print("   Please place 'Tables AS3000 2018.pdf' in /home/runner/app/")
        return
    
    print(f"\n📄 Test PDF: {test_pdf.name}")
    print(f"   Size: {test_pdf.stat().st_size / 1024 / 1024:.1f}MB")
    
    # Initialize table processor
    print("\n🔧 Initializing TableProcessor...")
    processor = TableProcessor()
    
    # Process tables
    print("\n🚀 Processing tables with Modal.com integration...")
    print("   (This may take 45-60 seconds for large PDFs)")
    print("   Note: Modal HTTP may timeout on large PDFs - falls back to OpenAI")
    
    try:
        tables = processor.process_tables(
            extracted_data={},
            page_map={},
            source_pdf_path=str(test_pdf),
            clauses=[]
        )
        
        print("\n✅ Processing completed successfully!")
        print(f"   Tables extracted: {len(tables)}")
        
        if len(tables) > 0:
            print("\n📊 Sample results:")
            for i, table in enumerate(tables[:5], 1):
                detection_method = getattr(table, 'detection_method', 'unknown')
                confidence = getattr(table, 'confidence', 0.0)
                page = getattr(table, 'page', 0)
                table_number = getattr(table, 'table_number', 'unknown')
                
                print(f"   {i}. {table_number} (page {page})")
                print(f"      Method: {detection_method}")
                print(f"      Confidence: {confidence:.2f}")
            
            if len(tables) > 5:
                print(f"   ... and {len(tables) - 5} more tables")
        
        # Analyze detection methods
        print("\n📈 Detection method breakdown:")
        modal_count = sum(1 for t in tables if getattr(t, 'detection_method', '') == 'modal_table_transformer')
        openai_count = sum(1 for t in tables if 'openai' in getattr(t, 'detection_method', '').lower())
        geometric_count = len(tables) - modal_count - openai_count
        
        if modal_count > 0:
            print(f"   🚀 Modal.com: {modal_count} tables ({modal_count/len(tables)*100:.1f}%)")
        if openai_count > 0:
            print(f"   🤖 OpenAI: {openai_count} tables ({openai_count/len(tables)*100:.1f}%)")
        if geometric_count > 0:
            print(f"   📐 Geometric: {geometric_count} tables ({geometric_count/len(tables)*100:.1f}%)")
        
        print("\n" + "=" * 70)
        print("✅ INTEGRATION TEST COMPLETED SUCCESSFULLY")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ Error during processing: {e}")
        print("\nStack trace:")
        import traceback
        traceback.print_exc()
        print("\n" + "=" * 70)
        print("❌ INTEGRATION TEST FAILED")
        print("=" * 70)
        sys.exit(1)


if __name__ == "__main__":
    test_modal_integration()
