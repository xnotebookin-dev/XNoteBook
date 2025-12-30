"""
XNoteBook Configuration File
Contains all application settings and constants
"""

import os
from datetime import timedelta

# Get the absolute path of the directory where this file is located
# This ensures paths work correctly on Render's ephemeral filesystem
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    """Base configuration class"""

    # Application Settings
    APP_NAME = "XNoteBook"
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'

    # Flask Settings
    DEBUG = False
    TESTING = False

    # File Upload Settings - Use absolute paths
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    PROCESSED_FOLDER = os.path.join(BASE_DIR, 'processed')
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB max file size
    ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'pdf'}

    # Database Settings - Use absolute path
    DATABASE_PATH = os.path.join(BASE_DIR, 'analytics.db')

    # OCR Settings
    OCR_DPI = 300
    OCR_LANGUAGE = ['en']
    USE_GPU = False

    # Session Settings
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # Rate Limiting
    RATELIMIT_STORAGE_URL = 'memory://'
    RATELIMIT_DEFAULT = "100 per hour"

    # Logging
    LOG_LEVEL = 'INFO'
    LOG_FILE = os.path.join(BASE_DIR, 'xnotebook.log')


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    SESSION_COOKIE_SECURE = False


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    SECRET_KEY = os.environ.get('SECRET_KEY')


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    DATABASE_PATH = ':memory:'


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
