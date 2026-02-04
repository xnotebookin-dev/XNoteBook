"""
XNoteBook - OCR Document Converter Web Application
Production-ready async architecture with proper job queue
"""

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file, send_from_directory
from werkzeug.utils import secure_filename
import os
import sqlite3
import uuid
import threading
from config import config
from datetime import datetime, timedelta
import time
from flask import make_response
from queue import Queue
from threading import Lock
import traceback

import torch
from transformers import AutoProcessor, Florence2ForConditionalGeneration
from datetime import datetime, timedelta
import os

# Import OCR processing functions
from pdf2image import convert_from_path
from PIL import Image
import pytesseract
import cv2
import fitz
import numpy as np

# Import TTS utilities
from utils.text_extractor import extract_text_from_file, clean_text_for_tts_advanced
from utils.audio_generator import add_smart_pauses, edge_tts_speak, generate_chunks_parallel, combine_audio_files
import asyncio


from utils import text_extractor, audio_generator

# ============================================
# TESSERACT PATH CONFIGURATION
# ============================================
tesseract_bin = "/usr/bin/tesseract"
if os.path.exists(tesseract_bin):
    pytesseract.pytesseract.tesseract_cmd = tesseract_bin

# Optional: GeoIP for location tracking
try:
    from geoip2 import database
    from geolite2 import geolite2
    GEOIP_AVAILABLE = True
except ImportError:
    GEOIP_AVAILABLE = False
    print("GeoIP not available. Install with: pip install python-geoip-geolite2")


# Initialize Flask application
app = Flask(__name__)
app.config.from_object(config['development'])

# Create required directories
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['PROCESSED_FOLDER'], exist_ok=True)

# Create audio output directory for TTS
AUDIO_OUTPUT_FOLDER = os.path.join(app.config['PROCESSED_FOLDER'], 'audio')
os.makedirs(AUDIO_OUTPUT_FOLDER, exist_ok=True)

# ============================================
# JOB QUEUE SYSTEM - PRODUCTION READY
# ============================================

class JobQueue:
    """Thread-safe job queue with worker pool"""

    def __init__(self, num_workers=2):
        self.queue = Queue()
        self.workers = []
        self.num_workers = num_workers
        self.lock = Lock()
        self.active_jobs = {}  # Track currently processing jobs

    def start(self):
        """Start worker threads"""
        for i in range(self.num_workers):
            worker = threading.Thread(target=self._worker, daemon=True, name=f"Worker-{i+1}")
            worker.start()
            self.workers.append(worker)
        print(f"✅ Started {self.num_workers} worker threads")

    def _worker(self):
        """Worker thread that processes jobs from queue"""
        while True:
            try:
                job = self.queue.get()
                if job is None:  # Poison pill to stop worker
                    break

                job_id = job['job_id']
                job_type = job.get('job_type', 'ocr')  # Default to OCR for backward compatibility

                # Mark job as active
                with self.lock:
                    self.active_jobs[job_id] = {
                        'started_at': datetime.now(),
                        'thread_name': threading.current_thread().name,
                        'job_type': job_type
                    }

                print(f"[{threading.current_thread().name}] Starting {job_type} job: {job_id}")

                # Process based on job type
                if job_type == 'tts':
                    process_tts_job(
                        job['job_id'],
                        job.get('text'),
                        job.get('file_path'),
                        job.get('voice', 'en-US-AriaNeural')
                    )
                else:
                    # Original OCR processing
                    process_document(
                        job['input_path'],
                        job['output_path'],
                        job_id
                    )

                # Remove from active jobs
                with self.lock:
                    self.active_jobs.pop(job_id, None)

                self.queue.task_done()

            except Exception as e:
                print(f"Worker error: {e}")
                traceback.print_exc()

    def add_job(self, job_id, input_path=None, output_path=None, job_type='ocr', **kwargs):
        """Add a job to the queue - supports both OCR and TTS jobs"""
        job = {
            'job_id': job_id,
            'job_type': job_type,
            'queued_at': datetime.now()
        }

        # Add OCR-specific fields
        if input_path:
            job['input_path'] = input_path
        if output_path:
            job['output_path'] = output_path

        # Add any additional kwargs (for TTS: text, file_path, voice)
        job.update(kwargs)

        self.queue.put(job)

        # Get queue position
        queue_position = self.queue.qsize()
        print(f"📋 {job_type.upper()} Job {job_id} added to queue (position: {queue_position})")
        return queue_position

    def get_queue_info(self):
        """Get current queue status"""
        with self.lock:
            return {
                'queue_size': self.queue.qsize(),
                'active_jobs': len(self.active_jobs),
                'active_job_ids': list(self.active_jobs.keys())
            }

# Initialize global job queue
job_queue = JobQueue(num_workers=2)

# ============================================
# TESSERACT CONFIGURATION
# ============================================
OPTIMIZED_DPI = 150

print("="*50)
print("🚀 TESSERACT OCR READY")
print("="*50)

try:
    version = pytesseract.get_tesseract_version()
    print(f"✅ Tesseract version: {version}")
    print(f"📊 Processing DPI: {OPTIMIZED_DPI}")
except Exception as e:
    print(f"⚠️ Tesseract not found: {e}")

print("="*50)

# ============================================
# FLORENCE-2 MODEL INITIALIZATION
# ============================================
device = "cuda" if torch.cuda.is_available() else "cpu"
torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32

model_id = "florence-community/Florence-2-base"

print(f"Loading {model_id}...")
model = Florence2ForConditionalGeneration.from_pretrained(
    model_id,
    torch_dtype=torch_dtype
).to(device)

processor = AutoProcessor.from_pretrained(model_id)

# ============================================
# DATABASE SETUP
# ============================================

def get_db_connection():
    """Get thread-safe database connection"""
    conn = sqlite3.connect(app.config['DATABASE_PATH'], check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    """Initialize SQLite database with required tables"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create visits table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS visits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address TEXT NOT NULL,
            user_agent TEXT,
            page TEXT NOT NULL,
            country TEXT,
            city TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create uploads table with enhanced status tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS uploads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT UNIQUE NOT NULL,
            filename TEXT NOT NULL,
            file_size INTEGER,
            file_type TEXT,
            ip_address TEXT,
            country TEXT,
            city TEXT,
            status TEXT DEFAULT 'queued',
            queue_position INTEGER,
            progress_percent INTEGER DEFAULT 0,
            current_step TEXT,
            error_message TEXT,
            upload_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            processing_started_timestamp DATETIME,
            processed_timestamp DATETIME,
            processing_time REAL
        )
    ''')

    # === MIGRATION FIX: Check and add missing columns for existing databases ===
    try:
        cursor.execute("PRAGMA table_info(uploads)")
        existing_columns = {row['name'] for row in cursor.fetchall()}

        # Define columns that might be missing in older DB versions
        new_columns = {
            'queue_position': 'INTEGER',
            'progress_percent': 'INTEGER DEFAULT 0',
            'current_step': 'TEXT',
            'error_message': 'TEXT',
            'processing_started_timestamp': 'DATETIME',
            'processed_timestamp': 'DATETIME',
            'processing_time': 'REAL'
        }

        for col_name, col_type in new_columns.items():
            if col_name not in existing_columns:
                print(f"🔧 Migrating database: Adding column '{col_name}'")
                try:
                    cursor.execute(f"ALTER TABLE uploads ADD COLUMN {col_name} {col_type}")
                except Exception as e:
                    print(f"⚠️ Error adding column {col_name}: {e}")

    except Exception as e:
        print(f"⚠️ Migration check failed: {e}")

    # Create TTS jobs table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tts_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT UNIQUE NOT NULL,
            source_type TEXT NOT NULL,
            source_filename TEXT,
            source_file_size INTEGER,
            voice_name TEXT DEFAULT 'en-US-AriaNeural',
            text_length INTEGER,
            ip_address TEXT,
            status TEXT DEFAULT 'queued',
            queue_position INTEGER,
            progress_percent INTEGER DEFAULT 0,
            current_step TEXT,
            error_message TEXT,
            output_file_path TEXT,
            output_file_size INTEGER,
            upload_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            processing_started_timestamp DATETIME,
            processed_timestamp DATETIME,
            processing_time REAL
        )
    ''')

    conn.commit()
    conn.close()


with app.app_context():
    init_database()

def get_location_from_ip(ip_address):
    """Get geographic location from IP address using GeoIP"""
    if not GEOIP_AVAILABLE or ip_address in ['127.0.0.1', 'localhost']:
        return 'Unknown', 'Unknown'

    try:
        reader = geolite2.reader()
        match = reader.get(ip_address)
        if match:
            country = match.get('country', {}).get('names', {}).get('en', 'Unknown')
            city = match.get('city', {}).get('names', {}).get('en', 'Unknown')
            return country, city
    except Exception as e:
        print(f"GeoIP lookup error: {e}")

    return 'Unknown', 'Unknown'


def track_visit(page):
    """Track a page visit in the database"""
    try:
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        if ip_address:
            ip_address = ip_address.split(',')[0].strip()

        user_agent = request.headers.get('User-Agent', '')
        country, city = get_location_from_ip(ip_address)

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO visits (ip_address, user_agent, page, country, city)
            VALUES (?, ?, ?, ?, ?)
        ''', (ip_address, user_agent, page, country, city))

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error tracking visit: {e}")


def track_upload(job_id, filename, file_size, file_type, queue_position):
    """Track a document upload in the database"""
    try:
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        if ip_address:
            ip_address = ip_address.split(',')[0].strip()

        country, city = get_location_from_ip(ip_address)

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO uploads (job_id, filename, file_size, file_type, ip_address, country, city, queue_position, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued')
        ''', (job_id, filename, file_size, file_type, ip_address, country, city, queue_position))

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error tracking upload: {e}")


def update_upload_status(job_id, status, error_message=None, processing_time=None, progress=None, step=None):
    """Update the status of a document upload"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Build update query dynamically
        updates = ['status = ?']
        params = [status]

        if error_message is not None:
            updates.append('error_message = ?')
            params.append(error_message)

        if processing_time is not None:
            updates.append('processing_time = ?')
            params.append(processing_time)
            updates.append('processed_timestamp = CURRENT_TIMESTAMP')

        if progress is not None:
            updates.append('progress_percent = ?')
            params.append(progress)

        if step is not None:
            updates.append('current_step = ?')
            params.append(step)

        if status == 'processing':
            updates.append('processing_started_timestamp = CURRENT_TIMESTAMP')

        params.append(job_id)

        query = f"UPDATE uploads SET {', '.join(updates)} WHERE job_id = ?"
        cursor.execute(query, params)

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error updating upload status: {e}")

# ============================================
# CLEAN UP SCHEDULER
# ============================================

def cleanup_old_files(hours=24):
    """Delete files older than specified hours"""
    try:
        cutoff_time = time.time() - (hours * 3600)
        deleted_count = 0

        # Clean uploads folder
        upload_folder = app.config['UPLOAD_FOLDER']
        for filename in os.listdir(upload_folder):
            file_path = os.path.join(upload_folder, filename)
            if os.path.isfile(file_path):
                if os.path.getmtime(file_path) < cutoff_time:
                    os.remove(file_path)
                    deleted_count += 1
                    print(f"🗑️ Deleted old upload: {filename}")

        # Clean processed folder
        processed_folder = app.config['PROCESSED_FOLDER']
        for filename in os.listdir(processed_folder):
            file_path = os.path.join(processed_folder, filename)
            if os.path.isfile(file_path):
                if os.path.getmtime(file_path) < cutoff_time:
                    os.remove(file_path)
                    deleted_count += 1
                    print(f"🗑️ Deleted old processed file: {filename}")

        # Clean audio folder (TTS outputs)
        if os.path.exists(AUDIO_OUTPUT_FOLDER):
            for filename in os.listdir(AUDIO_OUTPUT_FOLDER):
                file_path = os.path.join(AUDIO_OUTPUT_FOLDER, filename)
                if os.path.isfile(file_path):
                    if os.path.getmtime(file_path) < cutoff_time:
                        os.remove(file_path)
                        deleted_count += 1
                        print(f"🗑️ Deleted old audio file: {filename}")

        print(f"✅ Cleanup complete: {deleted_count} files deleted")
        return deleted_count

    except Exception as e:
        print(f"⚠️ Cleanup error: {e}")
        return 0


def start_cleanup_scheduler(interval_hours=6, file_age_hours=24):
    """Run cleanup periodically in background"""

    def cleanup_task():
        while True:
            time.sleep(interval_hours * 3600)
            print(f"\n{'=' * 50}")
            print(f"🧹 Running scheduled cleanup (files older than {file_age_hours}h)")
            print(f"{'=' * 50}")
            cleanup_old_files(file_age_hours)

    thread = threading.Thread(target=cleanup_task, daemon=True)
    thread.start()
    print(f"✅ Cleanup scheduler started (every {interval_hours}h, deletes files older than {file_age_hours}h)")

# ============================================
# OCR PROCESSING FUNCTIONS WITH PROGRESS
# ============================================

def preprocess_image(image_path):
    """Preprocess image for better OCR results"""
    img = cv2.imread(image_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    thresh = cv2.adaptiveThreshold(
        blurred, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        11, 2
    )
    preprocessed_path = f"{image_path}_preprocessed.png"
    cv2.imwrite(preprocessed_path, thresh)
    return preprocessed_path


def input_to_images(input_path, dpi=300):
    """Convert PDF or image input to list of image paths"""
    images = []
    if input_path.lower().endswith(".pdf"):
        print(f"📄 Converting PDF to images at {dpi} DPI...")
        pages = convert_from_path(
            input_path,
            dpi=dpi,
            fmt='jpeg',
            jpegopt={'quality': 85, 'optimize': True}
        )
        for i, page in enumerate(pages):
            img_path = f"{input_path}_page_{i}.jpg"
            page.save(img_path, "JPEG", quality=85, optimize=True)
            images.append(img_path)
            print(f"  ✓ Page {i+1} converted")
    else:
        img = Image.open(input_path)
        max_dimension = 3000
        if max(img.size) > max_dimension:
            print(f"📏 Resizing large image...")
            ratio = max_dimension / max(img.size)
            new_size = tuple(int(dim * ratio) for dim in img.size)
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            resized_path = f"{input_path}_resized.jpg"
            img.save(resized_path, "JPEG", quality=85, optimize=True)
            images.append(resized_path)
        else:
            images.append(input_path)
    return images


def ocr_with_boxes(image_path):
    """Perform OCR using Florence-2 and return text blocks with bounding boxes"""
    image = Image.open(image_path).convert("RGB")
    prompt = "<OCR_WITH_REGION>"

    inputs = processor(text=prompt, images=image, return_tensors="pt").to(device, torch_dtype)

    generated_ids = model.generate(
        input_ids=inputs["input_ids"],
        pixel_values=inputs["pixel_values"],
        max_new_tokens=1024,
        num_beams=3
    )

    generated_text = processor.batch_decode(generated_ids, skip_special_tokens=False)[0]

    parsed_answer = processor.post_process_generation(
        generated_text,
        task=prompt,
        image_size=(image.width, image.height)
    )

    blocks = []
    quad_boxes = parsed_answer['<OCR_WITH_REGION>'].get('quad_boxes', [])
    labels = parsed_answer['<OCR_WITH_REGION>'].get('labels', [])

    for box, text in zip(quad_boxes, labels):
        real_box = [
            (box[0], box[1]),
            (box[2], box[3]),
            (box[4], box[5]),
            (box[6], box[7])
        ]
        blocks.append({
            "bbox": real_box,
            "text": text,
        })

    return blocks


def create_searchable_pdf(image_paths, all_blocks, output_pdf):
    """Create a searchable PDF with invisible text layer"""
    doc = fitz.open()

    for img_path, blocks in zip(image_paths, all_blocks):
        img = Image.open(img_path)
        width, height = img.size

        page = doc.new_page(width=float(width), height=float(height))
        page.insert_image(page.rect, filename=img_path, keep_proportion=True)

        for block in blocks:
            text = block["text"]
            bbox = block["bbox"]

            x1 = float(bbox[0][0])
            y1 = float(bbox[0][1])
            x2 = float(bbox[2][0])
            y2 = float(bbox[2][1])

            font_size = max(6.0, min(40.0, y2 - y1))

            if not text or font_size <= 0:
                continue

            try:
                page.insert_text(
                    fitz.Point(x1, y2),
                    text,
                    fontsize=float(font_size),
                    fontname="helv",
                    render_mode=3,
                    overlay=True
                )
            except Exception as e:
                print(f"  ⚠️ Skipping text block: {e}")

    doc.save(output_pdf, garbage=4, deflate=True, clean=True)
    doc.close()


def process_document(input_path, output_pdf, job_id):
    """Main function to process document with progress tracking"""
    start_time = datetime.now()

    try:
        print(f"\n{'='*50}")
        print(f"📄 Processing Job: {job_id}")
        print(f"📁 File: {os.path.basename(input_path)}")
        print(f"{'='*50}")

        # Update status to processing
        update_upload_status(job_id, 'processing', progress=5, step='Starting conversion')

        # Convert input to images
        image_paths = input_to_images(input_path, dpi=300)
        print(f"📄 Converted to {len(image_paths)} page(s)")
        update_upload_status(job_id, 'processing', progress=15, step=f'Converted to {len(image_paths)} pages')

        # Perform OCR on each image with progress updates
        all_blocks = []
        total_pages = len(image_paths)

        for i, img in enumerate(image_paths):
            progress = 15 + int((i / total_pages) * 70)  # 15% to 85%
            update_upload_status(
                job_id,
                'processing',
                progress=progress,
                step=f'Processing page {i+1} of {total_pages}'
            )

            print(f"🔍 OCR processing page {i+1}/{total_pages}...")
            blocks = ocr_with_boxes(img)
            all_blocks.append(blocks)
            print(f"  ✓ Found {len(blocks)} text blocks")

        # Create searchable PDF
        update_upload_status(job_id, 'processing', progress=90, step='Creating searchable PDF')
        print(f"📝 Creating searchable PDF...")
        create_searchable_pdf(image_paths, all_blocks, output_pdf)

        # Get output file size
        output_size = os.path.getsize(output_pdf) / (1024 * 1024)
        print(f"💾 Output PDF: {output_size:.2f} MB")

        # Clean up temporary files
        update_upload_status(job_id, 'processing', progress=95, step='Cleaning up')
        print(f"🧹 Cleaning up temporary files...")
        for img in image_paths:
            if img != input_path:
                try:
                    os.remove(img)
                except:
                    pass

        # Calculate processing time
        processing_time = (datetime.now() - start_time).total_seconds()
        print(f"✅ COMPLETED in {processing_time:.1f} seconds")
        print(f"{'='*50}\n")

        # Update status to success
        update_upload_status(job_id, 'completed', processing_time=processing_time, progress=100, step='Complete')
        return True

    except Exception as e:
        processing_time = (datetime.now() - start_time).total_seconds()
        error_msg = f"{str(e)}\n{traceback.format_exc()}"
        print(f"❌ ERROR after {processing_time:.1f}s: {e}")
        print(traceback.format_exc())
        print(f"{'='*50}\n")
        update_upload_status(job_id, 'failed', error_msg, processing_time)
        return False


# ============================================
# TTS JOB PROCESSOR
# ============================================

def process_tts_job(job_id, text=None, file_path=None, voice='en-US-AriaNeural'):
    """
    Process text-to-speech job
    Handles both direct text and file input
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Update status to processing
        cursor.execute('''
            UPDATE tts_jobs 
            SET status = 'processing', 
                processing_started_timestamp = ?,
                current_step = 'Starting TTS processing'
            WHERE job_id = ?
        ''', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), job_id))
        conn.commit()

        # Step 1: Extract text if file provided
        if file_path and os.path.exists(file_path):
            cursor.execute('''
                UPDATE tts_jobs 
                SET current_step = 'Extracting text from file', 
                    progress_percent = 10
                WHERE job_id = ?
            ''', (job_id,))
            conn.commit()

            text = extract_text_from_file(file_path)
            print(f"Extracted {len(text)} characters from file")

        if not text or not text.strip():
            raise ValueError("No text to convert")

        # Step 2: Clean text for TTS
        cursor.execute('''
            UPDATE tts_jobs 
            SET current_step = 'Cleaning and preparing text', 
                progress_percent = 30
            WHERE job_id = ?
        ''', (job_id,))
        conn.commit()

        cleaned_text = clean_text_for_tts_advanced(
            text,
            remove_citations=True,
            expand_abbreviations=True,
            add_pauses=True
        )
        print(f"Cleaned text: {len(cleaned_text)} characters")

        # Step 3: Add smart pauses
        cursor.execute('''
            UPDATE tts_jobs 
            SET current_step = 'Adding natural pauses', 
                progress_percent = 50
            WHERE job_id = ?
        ''', (job_id,))
        conn.commit()

        enhanced_text = add_smart_pauses(cleaned_text)
        print(f"Enhanced text with pauses: {len(enhanced_text)} characters")

        # Step 4: Generate audio
        cursor.execute('''
            UPDATE tts_jobs 
            SET current_step = 'Generating audio', 
                progress_percent = 70
            WHERE job_id = ?
        ''', (job_id,))
        conn.commit()

        # Save audio file
        output_filename = f"{job_id}_audio.mp3"
        output_path = os.path.join(AUDIO_OUTPUT_FOLDER, output_filename)

        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            if len(enhanced_text) <= 5000:
                # Short text - direct generation
                loop.run_until_complete(edge_tts_speak(enhanced_text, voice, output_path))
            else:
                # Long text - chunked generation
                chunk_files = loop.run_until_complete(
                    generate_chunks_parallel(enhanced_text, voice, max_chunk_size=5000)
                )
                combine_audio_files(chunk_files, output_path)
        finally:
            loop.close()

        print(f"Audio saved to {output_path}")

        # Calculate file size
        file_size = os.path.getsize(output_path)

        # Get processing start time for duration calculation
        cursor.execute('SELECT processing_started_timestamp FROM tts_jobs WHERE job_id = ?', (job_id,))
        start_time_str = cursor.fetchone()[0]
        start_time = datetime.strptime(start_time_str, '%Y-%m-%d %H:%M:%S')
        processing_time = (datetime.now() - start_time).total_seconds()

        # Step 5: Complete
        cursor.execute('''
            UPDATE tts_jobs 
            SET status = 'completed',
                current_step = 'Completed',
                progress_percent = 100,
                processed_timestamp = ?,
                processing_time = ?,
                output_file_path = ?,
                output_file_size = ?
            WHERE job_id = ?
        ''', (
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            processing_time,
            output_path,
            file_size,
            job_id
        ))
        conn.commit()

        print(f"✅ TTS job {job_id} completed successfully")

    except Exception as e:
        error_message = str(e)
        print(f"❌ TTS job {job_id} failed: {error_message}")
        traceback.print_exc()

        cursor.execute('''
            UPDATE tts_jobs 
            SET status = 'failed',
                error_message = ?,
                processed_timestamp = ?
            WHERE job_id = ?
        ''', (error_message, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), job_id))
        conn.commit()

    finally:
        conn.close()


# ============================================
# HELPER FUNCTIONS
# ============================================

# TTS file extensions
TTS_FILE_EXTENSIONS = {'pdf', 'txt', 'doc', 'docx'}

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def allowed_tts_file(filename):
    """Check if file extension is allowed for TTS"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in TTS_FILE_EXTENSIONS


# ============================================
# FLASK ROUTES
# ============================================

@app.route('/health')
def health_check():
    """Health check endpoint for AWS Load Balancer"""
    try:
        version = pytesseract.get_tesseract_version()
        queue_info = job_queue.get_queue_info()

        return jsonify({
            'status': 'healthy',
            'ocr_engine': 'florence-2',
            'ocr_ready': True,
            'queue': queue_info,
            'timestamp': datetime.now().isoformat()
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'ocr_ready': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 503


@app.route('/warmup')
def warmup():
    """Warmup endpoint"""
    try:
        version = pytesseract.get_tesseract_version()
        return jsonify({
            'status': 'ready',
            'ocr_engine': 'florence-2',
            'ocr_loaded': True,
            'message': 'OCR system is ready',
            'processing_dpi': OPTIMIZED_DPI
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'ocr_loaded': False,
            'error': str(e)
        }), 500


@app.route('/')
def index():
    """Main upload page"""
    track_visit('index')
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload - returns immediately, queues for processing"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type. Please upload PDF or image files.'}), 400

    try:
        job_id = str(uuid.uuid4())
        filename = secure_filename(file.filename)

        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{job_id}_{filename}")
        file.save(upload_path)

        file_size = os.path.getsize(upload_path)
        file_type = filename.rsplit('.', 1)[1].lower()

        output_path = os.path.join(app.config['PROCESSED_FOLDER'], f"{job_id}_editable.pdf")

        # Add job to queue
        queue_position = job_queue.add_job(job_id, upload_path, output_path)

        # Track upload with queue position
        track_upload(job_id, filename, file_size, file_type, queue_position)

        session['job_id'] = job_id
        session['filename'] = filename

        # Get current queue info
        queue_info = job_queue.get_queue_info()

        # Return immediately with queue information
        return jsonify({
            'success': True,
            'job_id': job_id,
            'filename': filename,
            'queue_position': queue_position,
            'queue_info': queue_info,
            'message': 'File uploaded successfully and queued for processing'
        }), 200

    except Exception as e:
        print(f"Upload error: {e}")
        traceback.print_exc()
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500


@app.route('/processing')
def processing():
    """Processing status page"""
    track_visit('processing')
    return render_template('processing.html')


@app.route('/status/<job_id>')
def check_status(job_id):
    """Check processing status via API - Enhanced with progress"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT status, error_message, filename, processing_time,
                   upload_timestamp, processing_started_timestamp, processed_timestamp,
                   progress_percent, current_step, queue_position
            FROM uploads 
            WHERE job_id = ?
        ''', (job_id,))

        result = cursor.fetchone()
        conn.close()

        if result:
            row = dict(result)

            response = {
                'status': row['status'],
                'error_message': row['error_message'],
                'filename': row['filename'],
                'processing_time': row['processing_time'],
                'progress_percent': row['progress_percent'] or 0,
                'current_step': row['current_step'],
                'queue_position': row['queue_position']
            }

            # Calculate estimated time remaining
            if row['status'] == 'queued':
                queue_info = job_queue.get_queue_info()
                response['queue_info'] = queue_info
                response['estimated_wait_seconds'] = queue_info['queue_size'] * 600  # Estimate 10 min per job

            elif row['status'] == 'processing' and row['processing_started_timestamp']:
                start_time = datetime.strptime(row['processing_started_timestamp'], '%Y-%m-%d %H:%M:%S')
                elapsed = (datetime.now() - start_time).total_seconds()
                progress = row['progress_percent'] or 1

                if progress > 0:
                    estimated_total = elapsed / (progress / 100)
                    estimated_remaining = max(0, estimated_total - elapsed)
                    response['estimated_seconds_remaining'] = int(estimated_remaining)
                    response['elapsed_seconds'] = int(elapsed)

            return jsonify(response)
        else:
            return jsonify({'error': 'Job not found'}), 404

    except Exception as e:
        print(f"Status check error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/queue/status')
def queue_status():
    """Get current queue status"""
    try:
        queue_info = job_queue.get_queue_info()

        # Get queued jobs from database
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT job_id, filename, upload_timestamp, queue_position
            FROM uploads 
            WHERE status = 'queued'
            ORDER BY upload_timestamp ASC
        ''')
        queued_jobs = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return jsonify({
            'queue_info': queue_info,
            'queued_jobs': queued_jobs
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/result')
def result():
    """Result page"""
    track_visit('result')
    return render_template('result.html')


@app.route('/robots.txt')
def robots():
    """Serve robots.txt for search engines"""
    return send_file('robots.txt', mimetype='text/plain')


@app.route('/sitemap.xml')
def sitemap():
    """Generate dynamic sitemap"""
    pages = []

    pages.append({
        'loc': 'https://xnotebook.in/',
        'lastmod': datetime.now().strftime('%Y-%m-%d'),
        'changefreq': 'weekly',
        'priority': '1.0'
    })

    pages.append({
        'loc': 'https://xnotebook.in/analytics',
        'lastmod': datetime.now().strftime('%Y-%m-%d'),
        'changefreq': 'daily',
        'priority': '0.5'
    })

    pages.append({
        'loc': 'https://xnotebook.in/about',
        'lastmod': datetime.now().strftime('%Y-%m-%d'),
        'changefreq': 'daily',
        'priority': '0.5'
    })

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'

    for page in pages:
        xml += '  <url>\n'
        xml += f'    <loc>{page["loc"]}</loc>\n'
        xml += f'    <lastmod>{page["lastmod"]}</lastmod>\n'
        xml += f'    <changefreq>{page["changefreq"]}</changefreq>\n'
        xml += f'    <priority>{page["priority"]}</priority>\n'
        xml += '  </url>\n'

    xml += '</urlset>'

    response = make_response(xml)
    response.headers['Content-Type'] = 'application/xml'
    return response


@app.route('/download/<job_id>')
def download_file(job_id):
    """Download or Preview processed PDF"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT filename, status FROM uploads WHERE job_id = ?', (job_id,))
        result = cursor.fetchone()
        conn.close()

        if not result:
            return "Job not found", 404

        row = dict(result)

        if row['status'] != 'completed':
            return f"File not ready. Current status: {row['status']}", 400

        original_filename = row['filename']
        base_name = os.path.splitext(original_filename)[0]
        new_filename = f"editable_{base_name}.pdf"

        output_path = os.path.join(app.config['PROCESSED_FOLDER'], f"{job_id}_editable.pdf")

        if os.path.exists(output_path):
            return send_file(
                output_path,
                mimetype='application/pdf',
                as_attachment=False,
                download_name=new_filename
            )
        else:
            return "File not found", 404

    except Exception as e:
        print(f"Download error: {e}")
        traceback.print_exc()
        return "Download failed", 500

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/analytics')
def analytics():
    """Analytics dashboard showing visitor and upload statistics"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT COUNT(*) FROM (SELECT distinct(ip_address) FROM visits)')
        total_visits = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM uploads')
        total_uploads = cursor.fetchone()[0]

        cursor.execute('SELECT country, COUNT(*) as count FROM visits GROUP BY country ORDER BY count DESC LIMIT 10')
        visits_by_country = cursor.fetchall()

        cursor.execute('SELECT country, COUNT(*) as count FROM uploads GROUP BY country ORDER BY count DESC LIMIT 10')
        uploads_by_country = cursor.fetchall()

        cursor.execute('''
            SELECT filename, status, country, upload_timestamp, processing_time
            FROM uploads ORDER BY upload_timestamp DESC LIMIT 10
        ''')
        recent_uploads = cursor.fetchall()

        cursor.execute('''
            SELECT 
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                COUNT(*) as total,
                AVG(CASE WHEN status = 'completed' THEN processing_time END) as avg_time
            FROM uploads
        ''')
        status_stats = cursor.fetchone()
        conn.close()

        analytics_data = {
            'total_visits': total_visits,
            'total_uploads': total_uploads,
            'visits_by_country': visits_by_country,
            'uploads_by_country': uploads_by_country,
            'recent_uploads': recent_uploads,
            'success_rate': {
                'completed': status_stats[0] or 0,
                'failed': status_stats[1] or 0,
                'total': status_stats[2] or 0,
                'avg_processing_time': status_stats[3] or 0
            }
        }
        return render_template('analytics.html', data=analytics_data)
    except Exception as e:
        print(f"Analytics error: {e}")
        traceback.print_exc()
        return f"Error loading analytics: {e}", 500

# ============================================
# TEXT-TO-SPEECH API ENDPOINTS
# ============================================

@app.route('/api/tts/convert', methods=['POST'])
def convert_to_speech():
    """
    API endpoint to convert text or file to speech

    Accepts:
    - Form data with 'text' field (direct text input)
    - Form data with 'file' field (PDF, TXT, DOC, DOCX)
    - Optional 'voice' field (default: en-US-AriaNeural)

    Returns:
    - JSON with job_id for status tracking
    """
    try:
        # Get voice preference (optional)
        voice = request.form.get('voice', 'en-US-AriaNeural')

        # Validate voice name (basic validation)
        if not voice or not voice.strip():
            voice = 'en-US-AriaNeural'

        # Check if text or file is provided
        text_input = request.form.get('text', '').strip()
        file_input = request.files.get('file')

        if not text_input and not file_input:
            return jsonify({
                'error': 'Either text or file must be provided'
            }), 400

        # Prioritize file over text if both provided
        source_type = 'file' if file_input else 'text'

        # Generate unique job ID
        job_id = str(uuid.uuid4())

        # Get client info
        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if ip and ',' in ip:
            ip = ip.split(',')[0].strip()

        # Initialize variables
        file_path = None
        filename = None
        file_size = None
        text_length = len(text_input) if text_input else 0

        # Handle file upload
        if file_input:
            # Validate file extension
            if not allowed_tts_file(file_input.filename):
                return jsonify({
                    'error': f'Invalid file type. Allowed: {", ".join(TTS_FILE_EXTENSIONS)}'
                }), 400

            filename = secure_filename(file_input.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{job_id}_{filename}")
            file_input.save(file_path)
            file_size = os.path.getsize(file_path)

            print(f"📄 File uploaded: {filename} ({file_size} bytes)")

        # Save job to database
        conn = get_db_connection()
        cursor = conn.cursor()

        queue_position = job_queue.get_queue_info()['queue_size'] + 1

        cursor.execute('''
            INSERT INTO tts_jobs (
                job_id, source_type, source_filename, source_file_size,
                voice_name, text_length, ip_address, status, queue_position
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', ?)
        ''', (
            job_id, source_type, filename, file_size,
            voice, text_length, ip, queue_position
        ))
        conn.commit()
        conn.close()

        # Add job to queue
        job_queue.add_job(
            job_id=job_id,
            job_type='tts',
            text=text_input if text_input else None,
            file_path=file_path,
            voice=voice
        )

        return jsonify({
            'success': True,
            'job_id': job_id,
            'status': 'queued',
            'queue_position': queue_position,
            'message': 'TTS job submitted successfully'
        }), 202

    except Exception as e:
        print(f"TTS API error: {e}")
        traceback.print_exc()
        return jsonify({
            'error': f'Failed to process request: {str(e)}'
        }), 500


@app.route('/api/tts/status/<job_id>')
def tts_status(job_id):
    """
    Check status of TTS job

    Returns:
    - Job status, progress, and download link when completed
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM tts_jobs WHERE job_id = ?', (job_id,))
        result = cursor.fetchone()
        conn.close()

        if result:
            row = dict(result)

            response = {
                'job_id': job_id,
                'status': row['status'],
                'progress_percent': row['progress_percent'] or 0,
                'current_step': row['current_step'],
                'queue_position': row['queue_position'],
                'source_type': row['source_type'],
                'voice_name': row['voice_name']
            }

            # Add error message if failed
            if row['status'] == 'failed':
                response['error_message'] = row['error_message']

            # Add download link if completed
            if row['status'] == 'completed' and row['output_file_path']:
                response['download_url'] = url_for('download_tts_audio', job_id=job_id, _external=True)
                response['file_size'] = row['output_file_size']
                response['processing_time'] = row['processing_time']

            # Calculate estimated time remaining
            if row['status'] == 'queued':
                queue_info = job_queue.get_queue_info()
                response['queue_info'] = queue_info
                # Estimate 2 minutes per job in queue
                response['estimated_wait_seconds'] = queue_info['queue_size'] * 120

            elif row['status'] == 'processing' and row['processing_started_timestamp']:
                start_time = datetime.strptime(row['processing_started_timestamp'], '%Y-%m-%d %H:%M:%S')
                elapsed = (datetime.now() - start_time).total_seconds()
                progress = row['progress_percent'] or 1

                if progress > 0:
                    estimated_total = elapsed / (progress / 100)
                    estimated_remaining = max(0, estimated_total - elapsed)
                    response['estimated_seconds_remaining'] = int(estimated_remaining)
                    response['elapsed_seconds'] = int(elapsed)

            return jsonify(response)
        else:
            return jsonify({'error': 'Job not found'}), 404

    except Exception as e:
        print(f"TTS status check error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/tts/download/<job_id>')
def download_tts_audio(job_id):
    """
    Download generated audio file
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT output_file_path, source_filename, status FROM tts_jobs WHERE job_id = ?', (job_id,))
        result = cursor.fetchone()
        conn.close()

        if not result:
            return jsonify({'error': 'Job not found'}), 404

        row = dict(result)

        if row['status'] != 'completed':
            return jsonify({'error': f'Audio not ready. Current status: {row["status"]}'}), 400

        output_path = row['output_file_path']

        if not output_path or not os.path.exists(output_path):
            return jsonify({'error': 'Audio file not found'}), 404

        # Generate download filename
        base_name = os.path.splitext(row['source_filename'])[0] if row['source_filename'] else 'audio'
        download_name = f"{base_name}_audio.mp3"

        return send_file(
            output_path,
            mimetype='audio/mpeg',
            as_attachment=True,
            download_name=download_name
        )

    except Exception as e:
        print(f"TTS download error: {e}")
        traceback.print_exc()
        return jsonify({'error': 'Download failed'}), 500


@app.route('/api/tts/voices')
def list_voices():
    """
    List available TTS voices
    """
    voices = {
        'female': [
            {'name': 'en-US-AriaNeural', 'description': 'Friendly US English'},
            {'name': 'en-US-JennyNeural', 'description': 'Professional US English'},
            {'name': 'en-GB-SoniaNeural', 'description': 'British English'},
            {'name': 'en-AU-NatashaNeural', 'description': 'Australian English'},
            {'name': 'en-IN-NeerjaNeural', 'description': 'Indian English'}
        ],
        'male': [
            {'name': 'en-US-GuyNeural', 'description': 'Deep US English'},
            {'name': 'en-US-ChristopherNeural', 'description': 'Warm US English'},
            {'name': 'en-GB-RyanNeural', 'description': 'British English'},
            {'name': 'en-AU-WilliamNeural', 'description': 'Australian English'},
            {'name': 'en-IN-PrabhatNeural', 'description': 'Indian English'}
        ]
    }

    return jsonify(voices)


@app.route('/about')
def about():
    """About the app"""
    return render_template('about.html')

@app.route('/audio')
def audio():
    """About the app"""
    return render_template('audio.html')



# ... (rest of your app.py code above remains unchanged) ...

# ============================================
# PRODUCTION STARTUP
# ============================================
# Execute these immediately so Gunicorn starts the workers on import
with app.app_context():
    init_database()

print("🚀 Starting Background Workers...")
job_queue.start()

# Start automatic cleanup
start_cleanup_scheduler(interval_hours=6, file_age_hours=24)

# ============================================
# LOCAL DEVELOPMENT ENTRY POINT
# ============================================
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)