from docx import Document
import subprocess
import os
import re
import pymupdf4llm


def extract_pdf_content(pdf_path):
    """
    Extracts text from PDF, excluding headers and footers (top/bottom 8%).
    """
    md_text = pymupdf4llm.to_markdown(
        pdf_path,
        margins=(0, 70, 0, 50)
    )
    return md_text

def extract_text_from_word(file_path):
    """
    Extract text from .doc or .docx, excluding headers and footers.
    Requires LibreOffice for .doc conversion.
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext == '.doc':
        raise ValueError("Legacy .doc files are not supported. Please save as .docx first.")
    elif ext != '.docx':
        raise ValueError(f"Unsupported file format: {ext}")

    doc = Document(file_path)
    text_content = []
    for paragraph in doc.paragraphs:
        if paragraph.text.strip():
            text_content.append(paragraph.text)

    return '\n'.join(text_content)

def extract_text_from_txt(file_path, encoding='utf-8'):
    """
    Extract text from a text file, preserving special characters.
    """
    with open(file_path, 'r', encoding=encoding) as file:
        text = file.read()
    return text

def extract_text_from_file(file_path, encoding='utf-8'):
    """
    Main router function to extract text based on file extension.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()

    if ext == '.pdf':
        return extract_pdf_content(file_path)
    elif ext in ['.doc', '.docx']:
        return extract_text_from_word(file_path)
    elif ext == '.txt':
        return extract_text_from_txt(file_path, encoding)
    else:
        raise ValueError(f"Unsupported file format: {ext}")

def clean_text_for_tts(text, expand_abbreviations=True):
    """
    Stage 1: CLEANING
    Unwraps PDF text safely.
    Protects: Code blocks, Lists, and Headers from being merged into one line.
    """
    if not text or not isinstance(text, str):
        return ""

    # 1. Normalize line endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    # --- PROTECTION STEP: HIDE STRUCTURE ---
    # We replace strict formatting with placeholders so we don't accidentally delete their newlines.

    # A. Protect Code Blocks (``` code ```)
    # We hide the newlines inside code blocks
    def protect_code(match):
        return match.group(0).replace('\n', '<<CODE_NEWLINE>>')
    text = re.sub(r'```[\s\S]*?```', protect_code, text)

    # B. Protect List Items and Headers
    # If a line starts with *, -, #, or 1., we generally want to keep the newline before it.
    # We look for a newline followed by these characters.
    text = re.sub(r'\n(?=\s*[-*#]|\s*\d+\.)', '<<LIST_NEWLINE>>', text)

    # C. Protect Double Newlines (Paragraph Breaks)
    text = re.sub(r'\n\s*\n', '<<PARAGRAPH_BREAK>>', text)

    # --- UNWRAP STEP ---
    # Now it is safe to turn remaining single newlines into spaces
    text = text.replace('\n', ' ')

    # --- RESTORATION STEP ---
    text = text.replace('<<PARAGRAPH_BREAK>>', '\n\n')
    text = text.replace('<<LIST_NEWLINE>>', '\n')
    text = text.replace('<<CODE_NEWLINE>>', '\n')
    # -----------------------

    # 2. Fix broken hyphenation ("exam- ple" -> "example")
    text = re.sub(r'(\w+)-\s+(\w+)', r'\1\2', text)

    # 3. Strip Markdown Images and Links
    text = re.sub(r'!\[([^\]]*)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)

    # 4. Remove Citations [1]
    text = re.sub(r'\[\s*(?:\d+|[a-zA-Z]|note|source)\s*[-\d]*\s*\]', '', text, flags=re.IGNORECASE)

    # 5. Handle Tables (Pipes to commas)
    text = text.replace('|', ',')
    text = re.sub(r'\n\s*[-:,]+\s*\n', '\n', text)

    # 6. Remove Formatting Wrappers
    text = re.sub(r'[*_`]{1,3}([^*_`]+)[*_`]{1,3}', r'\1', text)

    # 7. Expand Abbreviations
    if expand_abbreviations:
        replacements = [
            (r'\bDr\.', 'Doctor'), (r'\bMr\.', 'Mister'),
            (r'\bMrs\.', 'Misses'), (r'\bMs\.', 'Miss'),
            (r'\bProf\.', 'Professor'), (r'\bSr\.', 'Senior'),
            (r'\bJr\.', 'Junior'), (r'\bvs\.', 'versus'),
            (r'\be\.g\.', 'for example,'), (r'\bi\.e\.', 'that is,'),
            (r'\betc\.', 'etcetera'), (r'\bFig\.', 'Figure'),
        ]
        for pattern, replacement in replacements:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    # 8. Clean symbols
    text = re.sub(r'[^\w\s.,!?;:\'\"\-#%$&()]', '', text)

    # 9. Final cleanup
    text = re.sub(r'[ \t]+', ' ', text)

    return text.strip()