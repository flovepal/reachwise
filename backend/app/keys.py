"""Print fresh secrets for .env:  python -m app.keys"""
import secrets

from cryptography.fernet import Fernet

if __name__ == "__main__":
    print(f"JWT_SECRET={secrets.token_urlsafe(48)}")
    print(f"ENCRYPTION_KEY={Fernet.generate_key().decode()}")
