"""
XNoteBook - OCR Document Converter Web Application
Main Flask application with visitor tracking and analytics
"""

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from werkzeug.utils import secure_filename
import os
import sqlite3
from datetime import datetime
import uuid
import threading
from config import config

# Import OCR processing functions
from pdf2image import convert_from_path
from PIL import Image
import easyocr
import cv2
import fitz

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

# Initialize EasyOCR reader (lazy loading)
ocr_reader = None


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
            processed_timestamp DATETIME
        )
    ''')

    conn.commit()
    conn.close()


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


def update_upload_status(job_id, status, error_message=None):
    """Update the status of a document upload"""
    try:
        conn = sqlite3.connect(app.config['DATABASE_PATH'])
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE uploads 
            SET status = ?, error_message = ?, processed_timestamp = CURRENT_TIMESTAMP
            WHERE job_id = ?
        ''', (status, error_message, job_id))

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error updating upload status: {e}")


# ============================================
# OCR PROCESSING FUNCTIONS
# ============================================

def get_ocr_reader():
    """Lazy load EasyOCR reader"""
    global ocr_reader
    if ocr_reader is None:
        ocr_reader = easyocr.Reader(
            app.config['OCR_LANGUAGE'],
            gpu=app.config['USE_GPU']
        )
    return ocr_reader


def input_to_images(input_path, dpi=300):
    """Convert PDF or image input to list of image paths"""
    images = []
    if input_path.lower().endswith(".pdf"):
        # Convert PDF pages to images
        pages = convert_from_path(input_path, dpi=dpi)
        for i, page in enumerate(pages):
            img_path = f"{input_path}_page_{i}.png"
            page.save(img_path, "PNG")
            images.append(img_path)
    else:
        # Already an image
        images.append(input_path)
    return images


def ocr_with_boxes(image_path):
    """Perform OCR on image and return text blocks with bounding boxes"""
    reader = get_ocr_reader()
    img = cv2.imread(image_path)
    results = reader.readtext(img)

    blocks = []
    for (bbox, text, conf) in results:
        blocks.append({
            "bbox": bbox,
            "text": text,
            "confidence": conf
        })
    return blocks


def create_searchable_pdf(image_paths, all_blocks, output_pdf):
    """Create a searchable PDF with invisible text layer"""
    doc = fitz.open()

    for img_path, blocks in zip(image_paths, all_blocks):
        img = Image.open(img_path)
        # Pillow 10+ Compatibility: Using Resampling.LANCZOS if resizing were needed
        width, height = img.size

        # Create new page with image
        page = doc.new_page(width=float(width), height=float(height))
        page.insert_image(page.rect, filename=img_path)

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
                    render_mode=3,  # Invisible text
                    overlay=True
                )
            except Exception as e:
                print(f"Skipping text due to error: {e}")

    # Save the PDF
    doc.save(output_pdf)
    doc.close()


def process_document(input_path, output_pdf, job_id):
    """Main function to process document with OCR"""
    try:
        # Convert input to images
        image_paths = input_to_images(input_path, dpi=app.config['OCR_DPI'])

        # Perform OCR on each image
        all_blocks = []
        for img in image_paths:
            blocks = ocr_with_boxes(img)
            all_blocks.append(blocks)

        # Create searchable PDF
        create_searchable_pdf(image_paths, all_blocks, output_pdf)

        # Clean up temporary image files
        for img in image_paths:
            if img != input_path:  # Don't delete original file
                try:
                    os.remove(img)
                except:
                    pass

        # Update status to success
        update_upload_status(job_id, 'completed')
        return True

    except Exception as e:
        print(f"Error processing document: {e}")
        update_upload_status(job_id, 'failed', str(e))
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

        thread = threading.Thread(
            target=process_document,
            args=(upload_path, output_path, job_id)
        )
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
            SELECT status, error_message, filename 
            FROM uploads 
            WHERE job_id = ?
        ''', (job_id,))

        result = cursor.fetchone()
        conn.close()

        if result:
            status, error_message, filename = result
            return jsonify({
                'status': status,
                'error_message': error_message,
                'filename': filename
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
            # mimetype is critical for iframe preview
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

        cursor.execute('SELECT filename, status, country, upload_timestamp FROM uploads ORDER BY upload_timestamp DESC LIMIT 10')
        recent_uploads = cursor.fetchall()

        cursor.execute('''
            SELECT 
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                COUNT(*) as total
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
                'total': status_stats[2] or 0
            }
        }
        return render_template('analytics.html', data=analytics_data)
    except Exception as e:
        return f"Error loading analytics: {e}", 500

if __name__ == '__main__':
    init_database()
    app.run(host='0.0.0.0', port=5000)
