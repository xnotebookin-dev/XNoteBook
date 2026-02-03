import pdfplumber
from docx import Document
import subprocess
import os
import re
import edge_tts
import nest_asyncio
import asyncio
from pydub import AudioSegment

def extract_pdf_content(pdf_path):
    """
    Extracts text from PDF, excluding headers and footers (top/bottom 8%).
    """
    content = ''
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_height = page.height
            header_threshold = page_height * 0.08
            footer_threshold = page_height * 0.92

            words = page.extract_words()

            filtered_text = []
            for word in words:
                word_top = word['top']
                word_bottom = word['bottom']

                if header_threshold < word_top and word_bottom < footer_threshold:
                    filtered_text.append(word['text'])

            content += ' '.join(filtered_text) + '\n\n'

    return content.strip()

def extract_text_from_word(file_path):
    """
    Extract text from .doc or .docx, excluding headers and footers.
    Requires LibreOffice for .doc conversion.
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext == '.doc':
        try:
            file_dir = os.path.dirname(file_path) or '.'
            subprocess.run(
                ['libreoffice', '--headless', '--convert-to', 'docx', '--outdir', file_dir, file_path],
                check=True,
                capture_output=True
            )
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            file_path = os.path.join(file_dir, f"{base_name}.docx")
        except subprocess.CalledProcessError as e:
            raise Exception(f"Failed to convert .doc to .docx: {e}")
        except FileNotFoundError:
            raise Exception("LibreOffice not found. Please install LibreOffice to convert .doc files.")

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

def clean_text_for_tts_advanced(text,
                                remove_citations=True,
                                expand_abbreviations=True,
                                remove_short_sentences=False,
                                min_sentence_words=3,
                                add_pauses=False,
                                pause_after_headings=True):
    """
    Cleans and prepares text specifically for high-quality TTS synthesis.
    """
    if not text or not isinstance(text, str):
        return ""

    # Remove URLs and Emails
    text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
    text = re.sub(r'\S+@\S+', '', text)

    # Remove brackets content
    text = re.sub(r'\[.*?\]|\(.*?\)|\{.*?\}', '', text)

    # Process Headings
    if pause_after_headings:
        lines = text.split('\n')
        processed_lines = []
        for line in lines:
            line_s = line.strip()
            if line_s and line_s.isupper() and len(line_s.split()) >= 2:
                processed_lines.append(' '.join(line_s) + '...')
            else:
                processed_lines.append(line)
        text = '\n'.join(processed_lines)

    # Remove Formatting & Code
    text = re.sub(r'[#*_`~<>]', '', text)
    text = re.sub(r'```.*?```|`.*?`', '', text, flags=re.DOTALL)

    if remove_citations:
        text = re.sub(r'\d{4}', '', text)

    if expand_abbreviations:
        abbreviations = {
            r'\bDr\.': 'Doctor', r'\bMr\.': 'Mister', r'\bMrs\.': 'Misses',
            r'\bMs\.': 'Miss', r'\bProf\.': 'Professor', r'\betc\.': 'etcetera',
            r'\be\.g\.': 'for example', r'\bi\.e\.': 'that is'
        }
        for abbr, replacement in abbreviations.items():
            text = re.sub(abbr, replacement, text, flags=re.IGNORECASE)

    # Punctuation & Whitespace
    text = re.sub(r'([!?.,:;]){3,}', r'\1\1', text)
    text = re.sub(r'\n\n+', '... ' if add_pauses else '. ', text)
    text = re.sub(r'\n', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()

    if remove_short_sentences:
        sentences = re.split(r'([.!?]+\s+)', text)
        cleaned = []
        for i in range(0, len(sentences), 2):
            s = sentences[i].strip()
            d = sentences[i+1] if i+1 < len(sentences) else ''
            if len(s.split()) >= min_sentence_words:
                cleaned.append(s + d.strip())
        text = ' '.join(cleaned)

    text = re.sub(r'[^\w\s.,!?;:\'-]', '', text)
    text = re.sub(r'\s+([.,!?;:])', r'\1', text)
    return re.sub(r'\s+', ' ', text).strip()