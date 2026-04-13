import os
import base64
import hashlib
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

def _get_fernet() -> Fernet:
    """Derives a Fernet key from the app's SECRET_KEY."""
    secret_key = os.getenv("SECRET_KEY")
    if not secret_key:
        raise RuntimeError("SECRET_KEY is not set in environment")
    
    # SECRET_KEY might be any length, but Fernet needs exactly 32 bytes (base64 encoded)
    key = hashlib.sha256(secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))

def encrypt_data(data: str) -> str:
    """Encrypts a string and returns a base64 encoded token."""
    f = _get_fernet()
    return f.encrypt(data.encode()).decode()

def decrypt_data(token: str) -> str:
    """Decrypts a base64 encoded token and returns the original string."""
    f = _get_fernet()
    return f.decrypt(token.encode()).decode()
