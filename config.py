"""
XNoteBook Configuration File
Contains all application settings and constants
"""

import os
from datetime import timedelta


class Config:
    """Base configuration class"""

    # Application Settings
    APP_NAME = "XNoteBook"
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'

    # Flask Settings
    DEBUG = False
    TESTING = False

    # File Upload Settings
    UPLOAD_FOLDER = 'uploads'
    PROCESSED_FOLDER = 'processed'
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB max file size
    ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'pdf'}

    # Database Settings
    DATABASE_PATH = 'analytics.db'

    # OCR Settings
    OCR_DPI = 300  # DPI for PDF to image conversion
    OCR_LANGUAGE = ['en']  # EasyOCR language support
    USE_GPU = False  # Set to True if GPU available

    # Session Settings
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)
    SESSION_COOKIE_SECURE = True  # Set to True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # Rate Limiting (if implemented)
    RATELIMIT_STORAGE_URL = 'memory://'
    RATELIMIT_DEFAULT = "100 per hour"

    # Logging
    LOG_LEVEL = 'INFO'
    LOG_FILE = 'xnotebook.log'


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    SESSION_COOKIE_SECURE = False  # Allow HTTP in development


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    # Override SECRET_KEY with environment variable
    SECRET_KEY = os.environ.get('SECRET_KEY')

    # Use PostgreSQL in production (optional)
    # DATABASE_URI = os.environ.get('DATABASE_URL')


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    DATABASE_PATH = ':memory:'  # Use in-memory database for tests


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}