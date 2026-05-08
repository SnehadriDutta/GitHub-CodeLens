from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request

def get_api_key(request: Request) -> str:
    return request.headers.get('x-api-key', get_remote_address(request))

limiter = Limiter(key_func=get_api_key)