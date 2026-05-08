import os
from jose import jwt, JWTError
from fastapi import Header, HTTPException
from dotenv import load_dotenv

load_dotenv(override=True)

SECRET_KEY=os.getenv('JWT_SECRET')
ALGORITHM=os.getenv('JWT_ALGORITHM')
VALID_CREDENTIALS = [username for username in os.getenv("VALID_CREDENTIALS", "").split(",")]



def create_token(username: str):
    payload = {
        'username': username
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token


async def validate_api_key(x_api_key: str = Header(...)) -> str:
    try:
        payload = jwt.decode(x_api_key, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get('username')
        if username not in VALID_CREDENTIALS:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return username
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")








