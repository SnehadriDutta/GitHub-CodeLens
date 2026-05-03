from typing import TypedDict, List, Dict, Any
from pydantic import BaseModel

class RepoState(TypedDict):
    query: str
    category: str
    repo_link: str
    web_results: List[Any]
    retrieved_chunks: List[Dict[str, Any]]
    messages: List[Any]
    response: str

class ProcessQueryResponse(TypedDict):
    category: str
    github_link: str
    query: str