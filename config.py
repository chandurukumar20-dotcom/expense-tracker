import os

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    """Application configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production-expense-tracker-2026')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'instance', 'expense_tracker.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    CURRENCY_SYMBOL = os.environ.get('CURRENCY_SYMBOL', '$')
    DEBUG = os.environ.get('FLASK_DEBUG', '1').lower() in ('true', '1', 't')
