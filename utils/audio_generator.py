import uuid

import edge_tts
from IPython.display import Audio
import asyncio
from pydub import AudioSegment

import os
import re



async def edge_tts_speak(text, voice_name, filename='output.mp3'):
    """Generate speech with edge-tts"""
    communicate = edge_tts.Communicate(text, voice_name, rate="-5%")
    await communicate.save(filename)
    return filename

def text_to_speech(text, voice='en-US-AriaNeural'):
    """
    Convert text to speech with custom voice

    Popular Voices:

    Female:
    - 'en-US-AriaNeural' (Friendly US)
    - 'en-US-JennyNeural' (Professional US)
    - 'en-GB-SoniaNeural' (British)
    - 'en-AU-NatashaNeural' (Australian)
    - 'en-IN-NeerjaNeural' (Indian)

    Male:
    - 'en-US-GuyNeural' (Deep US)
    - 'en-US-ChristopherNeural' (Warm US)
    - 'en-GB-RyanNeural' (British)
    - 'en-AU-WilliamNeural' (Australian)
    - 'en-IN-PrabhatNeural' (Indian)
    """
    loop = asyncio.get_event_loop()
    filename = 'clip.mp3'
    loop.run_until_complete(edge_tts_speak(text, voice, filename))
    return Audio(filename, autoplay=True)

def add_smart_pauses(text):
    """
    Generic function to add natural pauses to any text.
    Uses line breaks which edge-tts interprets as pauses (without speaking them).
    Works for stories, articles, technical docs, presentations, etc.
    """
    if not text or not text.strip():
        return text

    enhanced = text.strip()

    # 1. Preserve existing paragraph breaks (double newlines)
    # These already indicate major pauses
    enhanced = re.sub(r'\n\n+', '\n\n', enhanced)

    # 2. Add line break after sentences (period, exclamation, question mark)
    # This creates natural pauses between sentences
    enhanced = re.sub(r'([.!?])\s+([A-Z])', r'\1\n\2', enhanced)

    # 3. Detect section headers/titles (ALL CAPS or starting with #)
    # Add double line break after them for longer pause
    lines = enhanced.split('\n')
    processed_lines = []

    for i, line in enumerate(lines):
        stripped = line.strip()

        if not stripped:
            processed_lines.append('')
            continue

        # Check if line is a header
        is_header = False

        # Markdown header (starts with #)
        if stripped.startswith('#'):
            is_header = True
            stripped = re.sub(r'^#+\s*', '', stripped)  # Remove # symbols

        # ALL CAPS header (80%+ uppercase letters)
        alpha_chars = [c for c in stripped if c.isalpha()]
        if alpha_chars and not is_header:
            upper_ratio = sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars)
            if upper_ratio >= 0.8 and len(stripped.split()) <= 15:
                is_header = True

        # CHAPTER/SECTION/PART markers
        if re.match(r'^(CHAPTER|SECTION|PART|INTRODUCTION|CONCLUSION|SUMMARY|OVERVIEW)\b',
                   stripped, re.IGNORECASE):
            is_header = True

        # Add the line
        processed_lines.append(stripped)

        # Add extra line break after headers (unless it's the last line)
        if is_header and i < len(lines) - 1:
            processed_lines.append('')

    enhanced = '\n'.join(processed_lines)

    # 4. Handle lists - add line break before numbered/bulleted items
    # Matches: "1. Item", "1) Item", "- Item", "* Item", "• Item"
    enhanced = re.sub(r'\n(\d+[\.\)])\s+', r'\n\n\1 ', enhanced)
    enhanced = re.sub(r'\n([\-\*•])\s+', r'\n\n\1 ', enhanced)

    # 5. Add line break after colons when followed by list or explanation
    enhanced = re.sub(r':(\s*)(?=\n)', r':\n', enhanced)

    # 6. Clean up excessive line breaks (max 2 in a row)
    enhanced = re.sub(r'\n{3,}', '\n\n', enhanced)

    # 7. Ensure proper spacing after punctuation
    enhanced = re.sub(r'([.!?,;:])\s*([A-Za-z])', r'\1 \2', enhanced)

    # 8. Clean up multiple spaces
    enhanced = re.sub(r' +', ' ', enhanced)

    # 9. Remove spaces before punctuation
    enhanced = re.sub(r'\s+([,.!?;:])', r'\1', enhanced)

    # 10. Final cleanup
    enhanced = enhanced.strip()

    return enhanced

async def generate_chunks_parallel(text, voice_name, max_chunk_size=5000):
    """
    Generate audio chunks in parallel using your existing edge_tts_speak function.
    """
    chunks = split_text_into_chunks(text, max_chunk_size)
    print(f"Split text into {len(chunks)} chunks")

    # Create tasks for parallel generation
    tasks = []
    chunk_files = []

    for i, chunk in enumerate(chunks):
        chunk_filename = f'chunk_{i}.mp3'
        chunk_files.append(chunk_filename)
        # Use your existing edge_tts_speak function
        tasks.append(edge_tts_speak(chunk, voice_name, chunk_filename))

    print(f"Generating {len(chunks)} chunks in parallel...")
    await asyncio.gather(*tasks)

    return chunk_files


def combine_audio_files(chunk_files, output_filename='clip.mp3'):
    """
    Combine multiple audio files into one.
    """
    print("Combining audio chunks...")
    combined = AudioSegment.empty()

    for chunk_file in chunk_files:
        audio = AudioSegment.from_mp3(chunk_file)
        combined += audio
        # Clean up chunk file
        os.remove(chunk_file)

    # Export combined audio
    combined.export(output_filename, format='mp3')
    print(f"Audio saved to {output_filename}")

    return output_filename

def text_to_speech_long(text, voice='en-US-AriaNeural', max_chunk_size=5000):
    """
    Convert long text to speech with parallel processing.
    Automatically uses chunking for text > 5000 characters.

    Args:
        text (str): Text to convert
        voice (str): Voice name
        max_chunk_size (int): Characters per chunk (default: 5000)

    Returns:
        Audio: IPython Audio object for playback
    """
    filename = 'clip.mp3'

    # For short text, use the original function
    if len(text) <= max_chunk_size:
        return text_to_speech(text, voice)

    # For long text, use parallel chunking
    print(f"Processing long text ({len(text)} characters)...")
    loop = asyncio.get_event_loop()

    # Generate chunks in parallel
    chunk_files = loop.run_until_complete(
        generate_chunks_parallel(text, voice, max_chunk_size)
    )

    # Combine all chunks
    combine_audio_files(chunk_files, filename)

    return Audio(filename, autoplay=True)


def split_text_into_chunks(text, max_chunk_size=5000):
    """
    Split text into smaller chunks at sentence boundaries.

    Args:
        text (str): Text to split
        max_chunk_size (int): Maximum characters per chunk

    Returns:
        list: List of text chunks
    """
    # Split by sentences
    sentences = re.split(r'([.!?]+\s+)', text)

    chunks = []
    current_chunk = ""

    for i in range(0, len(sentences), 2):
        sentence = sentences[i]
        delimiter = sentences[i + 1] if i + 1 < len(sentences) else ''
        full_sentence = sentence + delimiter

        # If adding this sentence exceeds limit, save current chunk
        if len(current_chunk) + len(full_sentence) > max_chunk_size and current_chunk:
            chunks.append(current_chunk.strip())
            current_chunk = full_sentence
        else:
            current_chunk += full_sentence

    # Add remaining text
    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks
