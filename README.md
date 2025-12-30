# 📄 XNoteBook - OCR Document Converter

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-3.0.0-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

**XNoteBook** is a powerful web application that converts images and PDF documents into editable, searchable PDFs using advanced OCR (Optical Character Recognition) technology. Built with Flask and EasyOCR, it provides real-time visitor tracking and comprehensive analytics.

## ✨ Features

### Core Functionality
- 🖼️ **Image to Text**: Convert JPG, PNG images to searchable PDFs
- 📑 **PDF Processing**: Extract text from scanned PDFs
- 🎯 **High Accuracy OCR**: Powered by EasyOCR for reliable text extraction
- ⚡ **Real-time Processing**: Live status updates during conversion
- 💾 **Searchable PDFs**: Generated PDFs have invisible text layer for search/copy

### Analytics & Tracking
- 📊 **Visitor Analytics**: Track page visits and user engagement
- 🌍 **Geographic Insights**: See where your users are from
- 📈 **Upload Statistics**: Monitor document processing metrics
- 🎯 **Success Rate Tracking**: Analyze processing success/failure rates
- 🕐 **Real-time Dashboard**: Beautiful analytics dashboard

### User Experience
- 🎨 **Modern UI**: Clean, intuitive interface with smooth animations
- 📱 **Responsive Design**: Works on desktop, tablet, and mobile
- ⚡ **Fast Processing**: Optimized for quick document conversion
- 🔒 **Secure**: File validation and size limits
- 💬 **Status Updates**: Real-time processing feedback

## 🖼️ Screenshots

### Main Upload Interface
```
┌─────────────────────────────────┐
│   Document OCR Converter        │
│                                  │
│   [📄 Drop file or click]       │
│   Supports JPG, PNG, PDF         │
│                                  │
│   [Convert to Editable PDF]     │
└─────────────────────────────────┘
```

### Analytics Dashboard
```
┌─────────────────────────────────┐
│  📊 Analytics Dashboard          │
├─────────────────────────────────┤
│  👥 Visits  📄 Uploads  ✅ Success│
│  1,234      567         98%      │
├─────────────────────────────────┤
│  Visits by Country              │
│  India     ████████████ 450     │
│  USA       ████████ 320         │
│  UK        ██████ 250           │
└─────────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)
- Poppler (for PDF processing)

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/XNoteBook.git
cd XNoteBook
```

2. **Create virtual environment**
```bash
python -m venv venv

# Activate on Windows
venv\Scripts\activate

# Activate on Linux/Mac
source venv/bin/activate
```

3. **Install Python dependencies**
```bash
pip install -r requirements.txt
```

4. **Install system dependencies**

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install -y poppler-utils libsm6 libxext6
```

**macOS:**
```bash
brew install poppler
```

**Windows:**
Download from: https://github.com/oschwartz10612/poppler-windows/releases/

5. **Create required directories**
```bash
mkdir -p uploads processed
```

6. **Run the application**
```bash
python app.py
```

7. **Open in browser**
```
http://localhost:5000
```

## 📁 Project Structure

```
XNoteBook/
├── app.py                    # Main Flask application
├── config.py                 # Configuration settings
├── requirements.txt          # Python dependencies
├── analytics.db              # SQLite database (auto-created)
├── README.md                 # This file
├── uploads/                  # Uploaded files directory
├── processed/                # Processed PDFs directory
├── static/
│   └── css/
│       └── custom.css        # Custom styles (optional)
└── templates/
    ├── index.html            # Main upload page
    ├── processing.html       # Processing status page
    ├── result.html           # Result/download page
    ├── analytics.html        # Analytics dashboard
    ├── 404.html              # 404 error page
    └── 500.html              # 500 error page
```

## 🔧 Configuration

Edit `config.py` to customize settings:

```python
# File Upload Settings
MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB max file size
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'pdf'}

# OCR Settings
OCR_DPI = 300                    # PDF to image DPI
OCR_LANGUAGE = ['en']            # OCR language(s)
USE_GPU = False                  # Enable GPU acceleration

# Security
SECRET_KEY = 'your-secret-key'   # Change in production!
```

## 📊 Analytics Dashboard

Access the analytics dashboard at:
```
http://localhost:5000/analytics
```

### Available Metrics
- **Total Visits**: Number of page visits
- **Total Uploads**: Documents processed
- **Success Rate**: Processing success percentage
- **Geographic Distribution**: Visits and uploads by country
- **Recent Activity**: Latest uploads and processing status

### API Endpoint
Get analytics data programmatically:
```bash
curl http://localhost:5000/api/analytics
```

Response:
```json
{
  "total_visits": 1234,
  "total_uploads": 567,
  "regional_stats": [
    {"country": "India", "count": 450},
    {"country": "USA", "count": 320}
  ]
}
```

## 🔌 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main upload page |
| `/upload` | POST | Upload file for processing |
| `/processing` | GET | Processing status page |
| `/status/<job_id>` | GET | Check processing status |
| `/result` | GET | Result page |
| `/download/<job_id>` | GET | Download processed PDF |
| `/analytics` | GET | Analytics dashboard |
| `/api/analytics` | GET | Analytics data (JSON) |

## 🧪 Testing

Run the test suite:
```bash
python test_app.py
```

Test specific functionality:
```bash
# Test upload
curl -X POST -F "file=@test.jpg" http://localhost:5000/upload

# Test analytics API
curl http://localhost:5000/api/analytics
```

## 🚀 Production Deployment

### Using Gunicorn
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

### Using Docker
```bash
docker-compose up -d
```

### Using Systemd (Linux)
See `TESTING_AND_DEPLOYMENT.md` for detailed instructions.

## 🔒 Security Features

- ✅ File type validation (only JPG, PNG, PDF)
- ✅ File size limits (5MB maximum)
- ✅ Secure filename handling
- ✅ Session management
- ✅ CSRF protection ready
- ✅ SQL injection prevention (parameterized queries)
- ✅ XSS protection (template escaping)

### Production Security Checklist
- [ ] Change `SECRET_KEY` in config
- [ ] Enable HTTPS/SSL
- [ ] Set `SESSION_COOKIE_SECURE = True`
- [ ] Implement rate limiting
- [ ] Add user authentication (if needed)
- [ ] Regular security updates

## 🛠️ Technology Stack

### Backend
- **Flask 3.0.0** - Web framework
- **EasyOCR** - OCR engine
- **PyMuPDF (fitz)** - PDF manipulation
- **OpenCV** - Image processing
- **SQLite** - Database

### Frontend
- **HTML5** - Structure
- **CSS3** - Styling with animations
- **JavaScript** - Interactivity
- **Fetch API** - AJAX requests

### Optional
- **GeoIP2** - Geographic location
- **Gunicorn** - Production server
- **Redis** - Caching (optional)
- **Celery** - Background tasks (optional)

## 📖 Usage Examples

### Upload a Document
1. Visit http://localhost:5000
2. Click "Click to select a file" or drag & drop
3. Choose JPG, PNG, or PDF file (max 5MB)
4. Click "Convert to Editable PDF"
5. Wait for processing (status shown)
6. Download the converted PDF

### Check Analytics
1. Visit http://localhost:5000/analytics
2. View visitor statistics
3. See upload metrics by country
4. Monitor success rates

### API Usage
```python
import requests

# Upload file
with open('document.pdf', 'rb') as f:
    response = requests.post(
        'http://localhost:5000/upload',
        files={'file': f}
    )
    job_id = response.json()['job_id']

# Check status
status = requests.get(f'http://localhost:5000/status/{job_id}')
print(status.json())

# Download result
result = requests.get(f'http://localhost:5000/download/{job_id}')
with open('output.pdf', 'wb') as f:
    f.write(result.content)
```

## 🐛 Troubleshooting

### Common Issues

**Issue: "Poppler not found"**
```bash
sudo apt-get install poppler-utils
```

**Issue: "Permission denied" for uploads**
```bash
chmod -R 755 uploads processed
```

**Issue: "Database is locked"**
```bash
rm analytics.db
python app.py  # Will recreate database
```

**Issue: Port 5000 already in use**
```bash
# Change port in app.py
app.run(host='0.0.0.0', port=8080, debug=True)
```

## 📝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 👨‍💻 Author

**Your Name**
- GitHub: [@yourusername](https://github.com/yourusername)
- Email: your.email@example.com

## 🙏 Acknowledgments

- [EasyOCR](https://github.com/JaidedAI/EasyOCR) - OCR engine
- [Flask](https://flask.palletsprojects.com/) - Web framework
- [PyMuPDF](https://pymupdf.readthedocs.io/) - PDF processing
- [OpenCV](https://opencv.org/) - Computer vision library

## 📞 Support

If you encounter any issues or have questions:

1. Check the [Troubleshooting](#-troubleshooting) section
2. Review [closed issues](https://github.com/yourusername/XNoteBook/issues?q=is%3Aissue+is%3Aclosed)
3. Open a [new issue](https://github.com/yourusername/XNoteBook/issues/new)

## 🗺️ Roadmap

- [ ] Support for more languages (multi-language OCR)
- [ ] Batch processing (multiple files at once)
- [ ] User accounts and authentication
- [ ] Cloud storage integration (Google Drive, Dropbox)
- [ ] Email notifications
- [ ] API key system for programmatic access
- [ ] Machine learning text correction
- [ ] Document format detection
- [ ] Advanced image preprocessing
- [ ] Mobile app (iOS/Android)

---

**Made with ❤️ using Flask and EasyOCR**

**Star ⭐ this repository if you find it helpful!**