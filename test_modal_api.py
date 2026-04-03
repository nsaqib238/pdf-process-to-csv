"""
Test Modal.com API for table extraction
"""

import requests
import base64
import json
import sys

def test_modal_extraction(pdf_path: str, modal_url: str):
    """
    Test Modal.com table extraction API.
    
    Args:
        pdf_path: Path to PDF file
        modal_url: Your Modal endpoint URL
    """
    print(f"📄 Testing with: {pdf_path}")
    print(f"🌐 Modal URL: {modal_url}\n")
    
    # Read PDF
    try:
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
    except FileNotFoundError:
        print(f"❌ Error: File not found: {pdf_path}")
        return
    
    pdf_size_mb = len(pdf_bytes) / 1024 / 1024
    print(f"📦 PDF size: {pdf_size_mb:.1f}MB")
    
    # Encode to base64
    print("🔄 Encoding to base64...")
    pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")
    
    # Call Modal API
    print(f"📤 Sending to Modal.com...")
    try:
        response = requests.post(
            modal_url,
            json={
                "pdf_base64": pdf_base64,
                "filename": pdf_path.split("/")[-1]
            },
            timeout=600  # 10 minutes
        )
        
        if response.status_code == 200:
            result = response.json()
            
            if result.get("success"):
                print("\n" + "="*60)
                print("✅ SUCCESS")
                print("="*60)
                print(f"Tables found: {result['table_count']}")
                print(f"Pages processed: {result['pages_processed']}")
                print(f"Processing time: {result['processing_time']:.2f}s")
                print(f"Model: {result['model_info']['name']}")
                print(f"Device: {result['model_info']['device']}")
                
                # Show first 5 tables
                print(f"\n📊 First 5 tables:")
                for i, table in enumerate(result['tables'][:5], 1):
                    print(f"  {i}. Page {table['page']}: "
                          f"confidence {table['confidence']:.2%}, "
                          f"size {table['width']:.0f}x{table['height']:.0f}")
                
                if len(result['tables']) > 5:
                    print(f"  ... and {len(result['tables']) - 5} more")
                
                # Save results
                output_file = "modal_results.json"
                with open(output_file, "w") as f:
                    json.dump(result, f, indent=2)
                print(f"\n💾 Full results saved to: {output_file}")
                
                # Cost estimate
                gpu_seconds = result['processing_time']
                cost = (gpu_seconds / 3600) * 0.43  # T4 GPU $0.43/hour
                print(f"\n💰 Estimated cost: ${cost:.4f} (~$0.02/doc)")
                
            else:
                print(f"\n❌ Extraction failed: {result.get('error')}")
                if 'traceback' in result:
                    print(f"\nTraceback:\n{result['traceback']}")
        else:
            print(f"\n❌ HTTP Error: {response.status_code}")
            print(response.text)
            
    except requests.exceptions.Timeout:
        print("\n❌ Request timed out (>10 minutes)")
    except Exception as e:
        print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    # Update this with your Modal endpoint URL from deployment
    MODAL_URL = "YOUR_MODAL_ENDPOINT_URL_HERE"
    
    if MODAL_URL == "YOUR_MODAL_ENDPOINT_URL_HERE":
        print("⚠️  Please update MODAL_URL in this file with your actual endpoint!")
        print("Get it by running: modal deploy modal_table_extractor.py")
        sys.exit(1)
    
    # PDF path (update as needed)
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
    else:
        pdf_path = "backend/uploads/AS3000.pdf"  # Default
    
    test_modal_extraction(pdf_path, MODAL_URL)
