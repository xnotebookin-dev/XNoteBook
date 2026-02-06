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
    Stage 2: PAUSING & FLOW
    Adds structural pauses (newlines, colons) for Edge-TTS.
    """
    if not text: return ""

    enhanced = text

    # 1. PROTECT DECIMALS & INITIALS
    # Temporarily hide dots that are NOT sentence endings
    enhanced = re.sub(r'(\d)\.(\d)', r'\1<DOT>\2', enhanced) # 3.14
    enhanced = re.sub(r'(?<=\s)([A-Z])\.', r'\1<DOT>', enhanced) # T. Edison

    # 2. SENTENCE SPLITTING
    # Add a newline after punctuation if followed by a space and capital letter.
    # This forces the TTS engine to pause breath.
    enhanced = re.sub(r'([.!?;])\s+([A-Z])', r'\1\n\2', enhanced)

    # 3. RESTORE DOTS
    enhanced = enhanced.replace('<DOT>', '.')

    # 4. HEADER & LIST PROCESSING
    lines = enhanced.split('\n')
    processed_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # A. Detect Headers (Markdown # or All Caps)
        # Check for Markdown headers (# Header) or capitalized short lines
        is_header = stripped.startswith('#') or (stripped.isupper() and len(stripped.split()) < 10)

        if is_header:
            # Clean the '#' marker
            clean_line = stripped.lstrip('#').strip()
            # Add a colon if missing (Forces TTS to pause/intonate downwards)
            if clean_line and clean_line[-1] not in '.!:;':
                clean_line += ':'

            # Add buffer lines for isolation
            processed_lines.append("")
            processed_lines.append(clean_line)
            processed_lines.append("")

        # B. Detect List Items
        # Matches "1.", "1)", "-", "*" at start of line
        elif re.match(r'^(\d+[.)]|\*|-)\s+', stripped):
            # Ensure list items are on their own line
            processed_lines.append(stripped)

        # C. Standard Text
        else:
            processed_lines.append(stripped)

    # 5. Final Assembly
    result = '\n'.join(processed_lines)

    # Remove excessive blank lines created by the header logic
    result = re.sub(r'\n{3,}', '\n\n', result)

    return result.strip()


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
