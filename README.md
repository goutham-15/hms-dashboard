# Staff Information Extractor

A Python script to extract Staff ID and Staff Name from medical report PDFs.

## Features

- Extracts Staff ID (e.g., `SITT17ME01`)
- Extracts Staff Name (e.g., `Dr S Murali`)
- Supports single PDF file or batch processing of directories
- Uses multiple regex patterns for robust extraction
- Provides clear summary output

## Installation

Install the required dependencies:

```bash
pip3 install -r requirements.txt
```

Or install directly:

```bash
pip3 install PyPDF2
```

## Usage

### Process a single PDF file:

```bash
python3 extract_staff_info.py merged/1-murali_sitt17me01-dr-s-mura_134818.pdf
```

### Process all PDFs in a directory:

```bash
python3 extract_staff_info.py merged/
```

### First-page Tyrocare / SecondMedic extractor

Run `b.py` when you only need the details that live in the first page of Tyrocare or SecondMedic reports. The script renders the first page to an image (so it works even if the file lacks a searchable text layer) and then applies OCR + regex that look for the `Name` and `Emp ID` cells described in the project notes.

```bash
conda run -n local python b.py merged/1-murali_sitt17me01-dr-s-mura_134818.pdf
```

To process the full `merged/` folder and write a CSV:

```bash
conda run -n local python b.py merged --out staff_firstpage_results.csv
```

If you omit the path argument the script defaults to `merged/`. It OCRs only the first page of each PDF and extracts Staff ID and Staff Name for both Tyrocare's `Name : <ID> <Name>` line and SecondMedic's `Name | <Name>` / `Emp ID` first-row layout.

### Slice only the first page (PDF -> PDF)

Run `slice_first_page.py` when you want to create new PDFs that contain only page 1 from every PDF in a folder.

```bash
python3 slice_first_page.py merged --out first_pages
```

To run recursively:

```bash
python3 slice_first_page.py merged --out first_pages --recursive
```

Concurrency defaults to 5 workers (override with `--workers`):

```bash
python3 slice_first_page.py merged --out first_pages --workers 10
```

To save logs:

```bash
python3 slice_first_page.py merged --out first_pages --log-file logs/slice_first_page.log --log-level INFO
```

## Output Example

```
============================================================
Processing: merged/1-murali_sitt17me01-dr-s-mura_134818.pdf
============================================================

✓ Successfully extracted staff information:
  Staff ID:   SITT17ME01
  Staff Name: Dr S Murali

============================================================
SUMMARY
============================================================
Total files processed: 1

Extracted Information:

1. File: 1-murali_sitt17me01-dr-s-mura_134818.pdf
   Staff ID:   SITT17ME01
   Staff Name: Dr S Murali
```

## How It Works

The script:
1. Reads PDF files using PyPDF2
2. Extracts text content from all pages
3. Uses regex patterns to identify:
   - Staff ID format: `SITT` followed by alphanumeric characters
   - Staff Name: Doctor's name following the ID
4. Handles multiple format variations found in medical reports

## Supported Patterns

The script recognizes these patterns:
- `SITT17ME01 DR S MURALI (60Y/M)`
- `Name : Sitt17me01 Dr S Murali(60Y/M)`
- `Patient Name : SITT17ME01 DR S MURALI (60Y/M)`

## Requirements

- Python 3.6+
- PyPDF2 3.0.0+
- pdf2image
- pytesseract
- Pillow

## Project Structure

```
Dashboard/
├── extract_staff_info.py    # Main pipeline that OCRs and parses multi-page reports
├── b.py                     # First-page Tyrocare/SecondMedic extractor
├── requirements.txt          # Python dependencies
├── README.md                 # This file
└── merged/                   # Directory containing PDF files
    └── *.pdf                 # Medical report PDFs
```
