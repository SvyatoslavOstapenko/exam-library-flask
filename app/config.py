import os

SECRET_KEY = 'secret-key'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'instance', 'project.db')
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# ВАЖНО: для SQLite на Windows используем прямые слэши
SQLALCHEMY_DATABASE_URI = 'sqlite:///' + DB_PATH.replace('\\', '/')

SQLALCHEMY_TRACK_MODIFICATIONS = False
SQLALCHEMY_ECHO = True

UPLOAD_FOLDER = os.path.join(BASE_DIR, 'media', 'images')