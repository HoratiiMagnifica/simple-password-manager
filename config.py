import os
from datetime import timedelta

class Config:
    # Базовая конфигурация
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.urandom(32)
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///passwords.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Настройки безопасности
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)
    
    # Настройки шифрования
    ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY') or os.urandom(32)
    
    # Лимиты для защиты от брутфорса
    RATELIMIT_DEFAULT = "100 per day"
    RATELIMIT_STORAGE_URL = "memory://"
    
    # Параметры пароля
    PASSWORD_MIN_LENGTH = 12
    MAX_LOGIN_ATTEMPTS = 5
    LOCKOUT_TIME = timedelta(minutes=15)