"""
XNoteBook - OCR Document Converter Web Application
Tesseract-powered version for fast processing
"""

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from werkzeug.utils import secure_filename
import os
import sqlite3
from datetime import datetime
import uuid
import threading
from config import config

# Import OCR processing functions - USING TESSERACT
from pdf2image import convert_from_path
from PIL import Image
import pytesseract
import cv2
import fitz
import numpy as np

# ============================================
# TESSERACT PATH CONFIGURATION (ADDED)
# ============================================
# This is the specific fix for the "not in PATH" error on AWS
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

# ============================================
# TESSERACT CONFIGURATION
# ============================================
# Tesseract doesn't need model downloads - it's ready immediately!
OPTIMIZED_DPI = 150  # Using 150 DPI for 4x faster processing

print("="*50)
print("🚀 TESSERACT OCR READY")
print("="*50)

# Test Tesseract installation
try:
    version = pytesseract.get_tesseract_version()
    print(f"✅ Tesseract version: {version}")
    print(f"📊 Processing DPI: {OPTIMIZED_DPI}")
    print("⚡ No model download required - ready to process!")
except Exception as e:
    print(f"⚠️ Tesseract not found: {e}")
    print("⚠️ Install with: sudo apt-get install tesseract-ocr")

print("="*50)

# ============================================
# DATABASE SETUP AND HELPER FUNCTIONS
# ============================================

def init_database():
    """Initialize SQLite database with required tables"""
    conn = sqlite3.connect(app.config['DATABASE_PATH'])
    cursor = conn.cursor()

    # Create visits table for tracking page visits
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

    # Create uploads table for tracking document uploads
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
            status TEXT DEFAULT 'pending',
            error_message TEXT,
            upload_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
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

        conn = sqlite3.connect(app.config['DATABASE_PATH'])
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO visits (ip_address, user_agent, page, country, city)
            VALUES (?, ?, ?, ?, ?)
        ''', (ip_address, user_agent, page, country, city))

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error tracking visit: {e}")


def track_upload(job_id, filename, file_size, file_type):
    """Track a document upload in the database"""
    try:
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        if ip_address:
            ip_address = ip_address.split(',')[0].strip()

        country, city = get_location_from_ip(ip_address)

        conn = sqlite3.connect(app.config['DATABASE_PATH'])
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO uploads (job_id, filename, file_size, file_type, ip_address, country, city)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (job_id, filename, file_size, file_type, ip_address, country, city))

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error tracking upload: {e}")


def update_upload_status(job_id, status, error_message=None, processing_time=None):
    """Update the status of a document upload"""
    try:
        conn = sqlite3.connect(app.config['DATABASE_PATH'])
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE uploads 
            SET status = ?, error_message = ?, processed_timestamp = CURRENT_TIMESTAMP, processing_time = ?
            WHERE job_id = ?
        ''', (status, error_message, processing_time, job_id))

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error updating upload status: {e}")


# ============================================
# TESSERACT OCR PROCESSING FUNCTIONS
# ============================================

def preprocess_image(image_path):
    """Preprocess image for better OCR results"""
    img = cv2.imread(image_path)

    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Apply slight Gaussian blur to reduce noise
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)

    # Apply adaptive thresholding for better text detection
    thresh = cv2.adaptiveThreshold(
        blurred, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        11, 2
    )

    # Save preprocessed image
    preprocessed_path = f"{image_path}_preprocessed.png"
    cv2.imwrite(preprocessed_path, thresh)

    return preprocessed_path


def input_to_images(input_path, dpi=150):
    """Convert PDF or image input to list of image paths - OPTIMIZED"""
    images = []
    if input_path.lower().endswith(".pdf"):
        # Convert PDF pages to images at optimized DPI
        print(f"📄 Converting PDF to images at {dpi} DPI...")
        pages = convert_from_path(
            input_path,
            dpi=dpi,
            fmt='jpeg',  # JPEG is faster than PNG
            jpegopt={'quality': 85, 'optimize': True}
        )
        for i, page in enumerate(pages):
            img_path = f"{input_path}_page_{i}.jpg"
            page.save(img_path, "JPEG", quality=85, optimize=True)
            images.append(img_path)
            print(f"  ✓ Page {i+1} converted")
    else:
        # Optimize image if too large
        img = Image.open(input_path)
        max_dimension = 3000  # Limit max width/height
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
    """Perform OCR using Tesseract and return text blocks with bounding boxes"""
    # Preprocess image for better results
    processed_path = preprocess_image(image_path)

    # Get OCR data with bounding boxes
    # PSM 3 = Fully automatic page segmentation (best for documents)
    # OEM 3 = Default OCR Engine Mode (best accuracy)
    custom_config = r'--oem 3 --psm 3'

    data = pytesseract.image_to_data(
        processed_path,
        output_type=pytesseract.Output.DICT,
        config=custom_config
    )

    blocks = []
    n_boxes = len(data['text'])

    for i in range(n_boxes):
        # Filter by confidence (skip low confidence detections)
        if int(data['conf'][i]) > 30:
            text = data['text'][i].strip()
            if text:  # Skip empty text
                x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]

                # Convert to corner coordinates format (matching EasyOCR format)
                bbox = [
                    [x, y],           # Top-left
                    [x + w, y],       # Top-right
                    [x + w, y + h],   # Bottom-right
                    [x, y + h]        # Bottom-left
                ]

                blocks.append({
                    "bbox": bbox,
                    "text": text,
                    "confidence": data['conf'][i] / 100.0  # Convert to 0-1 scale
                })

    # Clean up preprocessed image
    try:
        os.remove(processed_path)
    except:
        pass

    return blocks


def create_searchable_pdf(image_paths, all_blocks, output_pdf):
    """Create a searchable PDF with invisible text layer"""
    doc = fitz.open()

    for img_path, blocks in zip(image_paths, all_blocks):
        img = Image.open(img_path)
        width, height = img.size

        # Create new page with image
        page = doc.new_page(width=float(width), height=float(height))

        # Insert image with compression
        page.insert_image(
            page.rect,
            filename=img_path,
            keep_proportion=True
        )

        # Add invisible text layer
        for block in blocks:
            text = block["text"]
            bbox = block["bbox"]

            # Extract bounding box coordinates
            x1 = float(bbox[0][0])
            y1 = float(bbox[0][1])
            x2 = float(bbox[2][0])
            y2 = float(bbox[2][1])

            # Calculate appropriate font size
            font_size = max(6.0, min(40.0, y2 - y1))

            # Skip empty or invalid text
            if not text or font_size <= 0:
                continue

            try:
                # Insert invisible text
                page.insert_text(
                    fitz.Point(x1, y2),
                    text,
                    fontsize=float(font_size),
                    fontname="helv",
                    render_mode=3,  # Invisible text (searchable but not visible)
                    overlay=True
                )
            except Exception as e:
                print(f"  ⚠️ Skipping text block: {e}")

    # Save the PDF with compression
    doc.save(
        output_pdf,
        garbage=4,      # Maximum garbage collection
        deflate=True,   # Compress streams
        clean=True      # Remove redundant objects
    )
    doc.close()


def process_document(input_path, output_pdf, job_id):
    """Main function to process document with Tesseract OCR"""
    start_time = datetime.now()

    try:
        print(f"\n{'='*50}")
        print(f"🔄 Processing Job: {job_id}")
        print(f"📁 File: {os.path.basename(input_path)}")
        print(f"{'='*50}")

        # Convert input to images
        image_paths = input_to_images(input_path, dpi=OPTIMIZED_DPI)
        print(f"📄 Converted to {len(image_paths)} page(s)")

        # Perform OCR on each image
        all_blocks = []
        for i, img in enumerate(image_paths):
            print(f"🔍 OCR processing page {i+1}/{len(image_paths)}...")
            blocks = ocr_with_boxes(img)
            all_blocks.append(blocks)
            print(f"  ✓ Found {len(blocks)} text blocks with avg confidence {sum([b['confidence'] for b in blocks])/len(blocks):.2%}" if blocks else "  ✓ No text detected")

        # Create searchable PDF
        print(f"📝 Creating searchable PDF...")
        create_searchable_pdf(image_paths, all_blocks, output_pdf)

        # Get output file size
        output_size = os.path.getsize(output_pdf) / (1024 * 1024)  # MB
        print(f"💾 Output PDF: {output_size:.2f} MB")

        # Clean up temporary image files
        print(f"🧹 Cleaning up temporary files...")
        for img in image_paths:
            if img != input_path:  # Don't delete original file
                try:
                    os.remove(img)
                except:
                    pass

        # Calculate processing time
        processing_time = (datetime.now() - start_time).total_seconds()
        print(f"✅ COMPLETED in {processing_time:.1f} seconds")
        print(f"{'='*50}\n")

        # Update status to success
        update_upload_status(job_id, 'completed', processing_time=processing_time)
        return True

    except Exception as e:
        processing_time = (datetime.now() - start_time).total_seconds()
        print(f"❌ ERROR after {processing_time:.1f}s: {e}")
        print(f"{'='*50}\n")
        update_upload_status(job_id, 'failed', str(e), processing_time)
        return False


# ============================================
# HELPER FUNCTIONS
# ============================================

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


# ============================================
# FLASK ROUTES
# ============================================

@app.route('/health')
def health_check():
    """Health check endpoint for AWS Load Balancer"""
    try:
        # Quick Tesseract version check
        version = pytesseract.get_tesseract_version()
        return jsonify({
            'status': 'healthy',
            'ocr_engine': 'tesseract',
            'ocr_version': str(version),
            'ocr_ready': True,
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
    """Warmup endpoint - Tesseract is always ready!"""
    try:
        version = pytesseract.get_tesseract_version()
        return jsonify({
            'status': 'ready',
            'ocr_engine': 'tesseract',
            'ocr_version': str(version),
            'ocr_loaded': True,
            'message': 'Tesseract OCR is ready (no model download needed)',
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
    """Handle file upload"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type'}), 400

    try:
        job_id = str(uuid.uuid4())
        filename = secure_filename(file.filename)

        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{job_id}_{filename}")
        file.save(upload_path)

        file_size = os.path.getsize(upload_path)
        file_type = filename.rsplit('.', 1)[1].lower()

        track_upload(job_id, filename, file_size, file_type)

        session['job_id'] = job_id
        session['filename'] = filename

        output_path = os.path.join(app.config['PROCESSED_FOLDER'], f"{job_id}_editable.pdf")

        # Start processing in background thread
        thread = threading.Thread(
            target=process_document,
            args=(upload_path, output_path, job_id)
        )
        thread.daemon = True  # Allow graceful shutdown
        thread.start()

        return jsonify({
            'success': True,
            'job_id': job_id,
            'filename': filename
        }), 200

    except Exception as e:
        print(f"Upload error: {e}")
        return jsonify({'error': 'Upload failed'}), 500


@app.route('/processing')
def processing():
    """Processing status page"""
    track_visit('processing')
    return render_template('processing.html')


@app.route('/status/<job_id>')
def check_status(job_id):
    """Check processing status via API"""
    try:
        conn = sqlite3.connect(app.config['DATABASE_PATH'])
        cursor = conn.cursor()

        cursor.execute('''
            SELECT status, error_message, filename, processing_time
            FROM uploads 
            WHERE job_id = ?
        ''', (job_id,))

        result = cursor.fetchone()
        conn.close()

        if result:
            status, error_message, filename, processing_time = result
            return jsonify({
                'status': status,
                'error_message': error_message,
                'filename': filename,
                'processing_time': processing_time
            })
        else:
            return jsonify({'error': 'Job not found'}), 404

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/result')
def result():
    """Result page"""
    track_visit('result')
    return render_template('result.html')


@app.route('/download/<job_id>')
def download_file(job_id):
    """Download or Preview processed PDF"""
    try:
        conn = sqlite3.connect(app.config['DATABASE_PATH'])
        cursor = conn.cursor()
        cursor.execute('SELECT filename FROM uploads WHERE job_id = ?', (job_id,))
        result = cursor.fetchone()
        conn.close()

        if not result:
            return "Job not found", 404

        original_filename = result[0]
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
        return "Download failed", 500


@app.route('/analytics')
def analytics():
    """Analytics dashboard showing visitor and upload statistics"""
    try:
        conn = sqlite3.connect(app.config['DATABASE_PATH'])
        cursor = conn.cursor()

        cursor.execute('SELECT COUNT(*) FROM visits')
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
        return f"Error loading analytics: {e}", 500


if __name__ == '__main__':
    with app.app_context():
        init_database()

    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)