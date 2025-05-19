import bcrypt
from jose import jwt
from datetime import datetime, timedelta

SECRET_KEY = "your-super-secret"
ALGORITHM = "HS256"
EXPIRE_DAYS = 30

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())

def create_access_token(data: dict):
    expire = datetime.utcnow() + timedelta(days=EXPIRE_DAYS)
    to_encode = data.copy()
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
