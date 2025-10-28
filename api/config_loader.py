import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# General server settings
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8000))
ENABLE_PREDICTION = os.getenv("ENABLE_PREDICTION", "0") == "1"
ENABLE_DEMO = os.getenv("ENABLE_DEMO", "0") == "1"
ENABLE_AUTHENTICATION = os.getenv("ENABLE_AUTHENTICATION", "0") == "1"

# Database
MYSQL_HOST = os.getenv("MYSQL_HOST", "mysql")
MYSQL_USER = os.getenv("MYSQL_USER", "sail")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "password")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "laravel")

# JWT
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "random_long_string_of_charactes")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_TOKEN_EXPIRE_MINUTES", 60))
