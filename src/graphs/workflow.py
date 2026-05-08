import re
import base64
import os
from typing import List, Dict, Any
from dotenv import load_dotenv
from datetime import datetime
from github import Auth, Github
from pathlib import Path
from tavily import TavilyClient
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue, VectorParams, Distance,PayloadSchemaType
from src.backend.ast_chunking import chunk_code_file
from concurrent.futures import ThreadPoolExecutor, as_completed
load_dotenv(override=True)

GITHUB_API_KEY=os.getenv('GITHUB_API_KEY')
QDRANT_API_KEY=os.getenv("QDRANT_API_KEY")
QDRANT_CLUSTER=os.getenv("QDRANT_CLUSTER")
TAVILY_API_KEY=os.getenv('TAVILY_API_KEY')

MAX_FILE_SIZE_KB=500
MAX_FILES=300
SUPPORTED_EXTENSIONS = {
    '.py', '.js', '.ts', '.jsx', '.tsx','.java', 
    '.go', '.rs', '.cpp', '.c', '.cs', '.md'}
SKIP_PATTERNS = {
    "node_modules/", "dist/", "build/", ".git/", "__pycache__/",
    "vendor/", "migrations/", ".min.js", ".bundle.js", ".venv/", 'venv/'
}
tavily_client = TavilyClient(api_key=TAVILY_API_KEY)
response = tavily_client.search("Who is Leo Messi?")

COLLECTION_NAME="codebase"
EMBEDDING_MODEL="sentence-transformers/all-MiniLM-L6-v2"
encoder = SentenceTransformer(EMBEDDING_MODEL)

auth = Auth.Token(GITHUB_API_KEY)
g = Github(auth=auth)

SKIP_PATTERNS = {
    "node_modules/", "dist/", "build/", ".git/", "__pycache__/",
    "vendor/", "migrations/", ".min.js", ".bundle.js", ".venv/", 'venv/'
}

path="./qdrant_data"
client = QdrantClient(path=path)
collections = [c.name for c in client.get_collections().collections]
# create collection
if COLLECTION_NAME not in collections:
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=encoder.get_embedding_dimension(),
                                    distance=Distance.COSINE)
    )
    for field in ["owner", "repo"]:
        client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name=field,
            field_schema=PayloadSchemaType.KEYWORD
        )

class WorkFlow:

    @staticmethod
    def extract_github_url(text: str):
        # Regex pattern to match standard GitHub URLs
        pattern = r'(https?://(?:www\.)?github\.com/[^\s]+)'

        # Search for the pattern in the provided text
        match = re.search(pattern, text)

        # If a match is found, return it. Otherwise, return a blank string.
        if match:
            return match.group(0)
        else:
            return ""

    @staticmethod
    def extract_owner_repo(url: str):
        pattern = r'https://github.com/([^/]+)/([^/]+)'
        match = re.match(pattern, url)
        if match:
            return match.group(1), match.group(2)
        else:
            return None, None

    @staticmethod
    def check_repo_present_in_db(owner: str, repo: str,) -> bool:        
        repo_filter = Filter(
            must=[
                FieldCondition(key="owner", match=MatchValue(value=owner)),
                FieldCondition(key="repo", match=MatchValue(value=repo))
            ]
        )
        count_result = client.count(
            collection_name=COLLECTION_NAME,
            count_filter=repo_filter
        )
        count = count_result.count
        if count > 0:
            return True
        else:
            return False

    @staticmethod
    def fetch_repo(owner: str, repo: str) -> list:
        if owner and repo:
            contents = WorkFlow.get_github_repo(owner, repo)
            return contents
        else:
            return []
        
    @staticmethod
    def get_github_repo(owner: str, repo: str, branch: str = 'main'):

        repo = g.get_repo(f"{owner}/{repo}")
        contents = repo.get_git_tree(branch, recursive=True).tree

        files = []
        for item in contents:

            if len(files) >= MAX_FILES:
                break

            ext = Path(item.path).suffix
            if ext not in SUPPORTED_EXTENSIONS:
                continue

            if item.size > MAX_FILE_SIZE_KB * 1024:
                continue

            file_content = repo.get_contents(item.path, ref=branch)
            code = base64.b64decode(file_content.content).decode('utf-8', errors='ignore')

            files.append({
                "path": item.path,
                "content": code,
                "language": ext.lstrip('.'),
                "size": item.size,
                "repo": repo,
                "branch": branch
            })

        return files

    @staticmethod
    def get_github_repo_chunks(owner: str, repo: str, branch: str = 'main'):
        repo = g.get_repo(f"{owner}/{repo}")
        contents = repo.get_git_tree(branch, recursive=True).tree

        def fetch_and_chunk(item) -> list[dict] | None:
            file_content = repo.get_contents(item.path, ref=branch)
            code = base64.b64decode(file_content.content).decode('utf-8', errors='ignore')

            ext = Path(item.path).suffix
            file = {
                "path": item.path,
                "content": code,
                "language": ext.lstrip('.'),
                "size": item.size,
                "repo": repo,
                "branch": branch
            }

            if should_skip(file):
                return None
            
            return chunk_code_file(file)
        
        all_chunks = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(fetch_and_chunk, item): item for item in contents}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    all_chunks.append(result)
        return all_chunks

    @staticmethod
    def get_codebase_chunks(files: List[Any]):
        chunks = []
        for file in files:
            chunks.extend(chunk_code_file(file))
        return chunks

    @staticmethod
    def save_to_db(owner: str, repo:str, chunks: List[Any]):
        points = []
        for i, chunk in enumerate(chunks):
            vector = encoder.encode(chunk["text"]).tolist()
            point = PointStruct(
                id=get_ticks(),
                vector=vector,
                payload={**chunk,'owner': owner,'repo': repo, }
            )
            points.append(point)

        client.upsert(
            collection_name=COLLECTION_NAME,
            points=points
        )

    @staticmethod
    def fetch_from_db(query: str, repo_url: str):
        owner, repo = WorkFlow.extract_owner_repo(repo_url)
        query_vector = encoder.encode(query).tolist()
        query_filter = Filter(
            must=[
                FieldCondition(key="owner", match=MatchValue(value=owner)),
                FieldCondition(key="repo", match=MatchValue(value=repo))
            ]
        )
        results = client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            query_filter=query_filter,
            with_payload=True,
            limit=5,
        )
        db_result = []
        for item in results.points:
            db_result.append({
                'type': item.payload['type'],
                'language': item.payload['language'],
                'name': item.payload['name'],
                'code': item.payload['text']
            })
        return db_result

    @staticmethod
    def format_history(history: List[Dict[str,str]]):
        formatted_history = ''
        for conv in history:
            formatted_history += f'role: {conv['role']}\ncontent: {conv['content']}\n'
        return formatted_history

    @staticmethod
    def search_web(query: str):
        tavily_response = tavily_client.search(
            query=query,
            #include_domains=["github.com", "stackoverflow.com"]
            search_depth="advanced",
            time_range="week",
            chunks_per_source=5
        )
        return tavily_response

def get_ticks():
    dt = datetime.now()
    epoch = datetime(1, 1, 1)
    return int((dt - epoch).total_seconds() * 10**7)



def should_skip(file: dict) -> bool:
    path = file["path"].lower()
    if Path(file["path"]).suffix in SKIP_EXTENSIONS:
        return True
    if any(pat in path for pat in SKIP_PATTERNS):
        return True
    if len(file["content"].strip()) < 50:   # empty/trivial files
        return True
    return False





















