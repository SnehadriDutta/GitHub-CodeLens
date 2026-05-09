from win32comext.shell.demos.servers.folder_view import debug

from src.graphs.graph import handle_query, ingest_and_save_repo
from fastapi import FastAPI, Response, Form, Request, HTTPException
from typing import Annotated
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import asyncio
import uvicorn

app=FastAPI()
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

active_sessions = set()
active_ingests = set()

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={
            'error': "Rate Limit Exceeded",
            'code': 'RATE_LIMITED',
            'retry_after': 60
        }
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict):
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail
        )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": str(exc.detail),
            "code": "HTTP_ERROR"
        }
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            'error': 'Internal Server Error',
            'code': 'INTERNAL_SERVER_ERROR'
        }
    )


@app.post('/api/ingest')
@limiter.limit('10/minute')
async def ingest(request: Request, github_link: str, session_id: str):
    if session_id in active_sessions:
        raise HTTPException(
            status_code=409,
            detail={
                'error': 'A request is already processing for this session',
                'code': 'SESSION_BUSY'
            }
        )

    if github_link in active_ingests:
        raise HTTPException(
            status_code=409,
            detail={
                'error': 'Repository is already being ingested',
                'code': "INGEST_IN_PROGRESS"
            }
        )

    active_sessions.add(session_id)
    active_ingests.add(github_link)

    try:
        result  = await asyncio.wait_for(
            asyncio.to_thread(
            ingest_and_save_repo, github_link
            ),
            timeout=120
        )

        return result
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=408,
            detail={
                "error": "Repository processing timeout",
                "code": "PROCESSING_TIMEOUT"
            }
        )
    finally:
        active_ingests.discard(github_link)
        active_sessions.discard(session_id)



@app.post('/api/query', response_class=Response)
async def query(request: Request, user_query: str, github_link: str, session_id: str):
    if session_id in active_sessions:
        raise HTTPException(
            status_code=409,
            detail={
                'error': 'A request is already processing for this session',
                'code': 'SESSION_BUSY'
            }
        )

    if github_link in active_ingests:
        raise HTTPException(
            status_code=409,
            detail={
                'error': 'Repository is already being ingested',
                'code': "INGEST_IN_PROGRESS"
            }
        )

    active_sessions.add(session_id)
    active_ingests.add(github_link)

    active_sessions.add(session_id)
    active_ingests.add(github_link)

    try:
        response = await asyncio.wait_for(
            asyncio.to_thread(
                handle_query, user_query, github_link
            ),
            timeout=120
        )

        return JSONResponse({'response': response})
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=408,
            detail={
                "error": "Repository processing timeout",
                "code": "PROCESSING_TIMEOUT"
            }
        )
    finally:
        active_ingests.discard(github_link)
        active_sessions.discard(session_id)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=15000)

