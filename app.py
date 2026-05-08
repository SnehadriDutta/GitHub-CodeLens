from src.graphs.graph import handle_query
from fastapi import FastAPI, Response, Form, Depends, Request, HTTPException
from typing import Annotated
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import uvicorn

app=FastAPI()
#app.state.limiter = limiter
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


@app.post('/api/query', response_class=Response)
async def query(query: Annotated[str, Form()]):
    response = handle_query(query=query)
    return JSONResponse({'response': response})



if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=15000)

