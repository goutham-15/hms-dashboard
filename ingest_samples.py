#!/usr/bin/env python3
"""
Process sample PDF files and insert them into the database.
This script uses the DocumentIngestor pipeline to:
1. Extract text from PDFs (OCR)
2. Chunk the text
3. Store in Vector DB
4. Extract medical information using LLM
5. Insert into SQL database
6. Clear Redis cache
"""

import argparse
import os
from pathlib import Path
from app.pipeline.document_injest import DocumentIngestor
from app.utils.redis_client import RedisClient
from app.utils.logger import get_logger

logger = get_logger(name="ingest_samples")

# Default sample directory
SAMPLES_DIR = Path("/Users/103501/Desktop/Projects/hms-dashboard/sample")

def process_file(pdf_path: Path, redis_client: RedisClient) -> bool:
    """Process a single PDF file."""
    print(f"\n{'='*60}")
    print(f"Processing: {pdf_path.name}")
    print('='*60)
    
    try:
        # Initialize the ingestor
        ingestor = DocumentIngestor(pdf_path)
        
        # Run the full pipeline
        result = ingestor.process()
        
        print(f"✓ Successfully processed {pdf_path.name}")
        print(f"  Source ID: {result['source_id']}")
        print(f"  Pages extracted: {len(result.get('chunks', []))}")
        print(f"  Vector DB collection: {result.get('vector_db_collection')}")
        
        # Clear Redis cache since we added new data
        cleared = redis_client.clear_pattern("analytics:*")
        print(f"  Cache cleared: {cleared} keys")
        
        return True
        
    except Exception as e:
        print(f"✗ Error processing {pdf_path.name}")
        print(f"  Error: {str(e)}")
        logger.exception(f"Failed to process {pdf_path.name}")
        return False


def main():
    """Main entry point for sample ingestion."""
    parser = argparse.ArgumentParser(
        description="Process sample PDF files and insert into database."
    )
    parser.add_argument(
        "--filename",
        type=str,
        help="Specific PDF file to process."
    )
    parser.add_argument(
        "filenames",
        type=str,
        nargs="*",
        help="One or more PDF files to process."
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all PDF files in the sample directory."
    )
    
    args = parser.parse_args()
    
    # Initialize Redis client
    redis_client = RedisClient()
    
    # Check Redis connection
    if not redis_client.ping():
        print("⚠️  Warning: Redis is not available. Cache will not be cleared.")
    
    # Determine which files to process
    pdf_files = []
    
    if args.all:
        # Process all PDFs in sample directory
        if SAMPLES_DIR.exists():
            pdf_files = list(SAMPLES_DIR.glob("*.pdf"))
            print(f"Found {len(pdf_files)} PDF files in {SAMPLES_DIR}")
        else:
            print(f"Error: Sample directory not found: {SAMPLES_DIR}")
            return 1
    
    elif args.filename:
        # Process specific file
        pdf_path = Path(args.filename)
        if not pdf_path.exists():
            pdf_path = SAMPLES_DIR / args.filename
        
        if pdf_path.exists():
            pdf_files.append(pdf_path)
        else:
            print(f"Error: File not found: {args.filename}")
            return 1
    
    elif args.filenames:
        # Process multiple files
        for filename in args.filenames:
            pdf_path = Path(filename)
            if not pdf_path.exists():
                pdf_path = SAMPLES_DIR / filename
            
            if pdf_path.exists():
                pdf_files.append(pdf_path)
            else:
                print(f"Warning: File not found: {filename}")
    
    else:
        # No arguments - show usage
        print("No input files specified.")
        print("\nUsage:")
        print("  python ingest_samples.py --all                    # Process all PDFs in sample/")
        print("  python ingest_samples.py --filename sample.pdf    # Process specific file")
        print("  python ingest_samples.py file1.pdf file2.pdf      # Process multiple files")
        return 1
    
    if not pdf_files:
        print("No PDF files found to process.")
        return 1
    
    # Process each file
    print(f"\n{'='*60}")
    print(f"Starting ingestion of {len(pdf_files)} file(s)")
    print('='*60)
    
    success_count = 0
    failed_count = 0
    
    for pdf_path in pdf_files:
        if process_file(pdf_path, redis_client):
            success_count += 1
        else:
            failed_count += 1
    
    # Summary
    print(f"\n{'='*60}")
    print("Ingestion Summary")
    print('='*60)
    print(f"  Total files: {len(pdf_files)}")
    print(f"  Successful: {success_count}")
    print(f"  Failed: {failed_count}")
    print('='*60)
    
    if success_count > 0:
        print("\n✓ Data has been inserted into the database!")
        print("  You can now test the caching:")
        print("    curl http://localhost:8001/api/v1/analytics/summary")
        print("    curl http://localhost:8001/api/v1/analytics/records")
        print("  Or view in browser:")
        print("    http://localhost:8001/demo")
    
    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    exit(main())
