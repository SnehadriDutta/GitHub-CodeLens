from github import Auth, Github
from pathlib import Path
import json
import re
import base64
import os
from typing import List, Dict, Any
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
from src.githubprocessing.ast_chunking import chunk_code_file
load_dotenv(override=True)

GITHUB_API_KEY=os.getenv('GITHUB_API_KEY')
MAX_FILE_SIZE_KB=500
MAX_FILES=300
SUPPORTED_EXTENSIONS = {
    '.py', '.js', '.ts', '.jsx', '.tsx','.java',
    '.go', '.rs', '.cpp', '.c', '.cs', '.md'}
SKIP_PATTERNS = {
    "node_modules/", "dist/", "build/", ".git/", "__pycache__/",
    "vendor/", "migrations/", ".min.js", ".bundle.js", ".venv/", 'venv/'
}

github_ingested = []

auth = Auth.Token(GITHUB_API_KEY)
g = Github(auth=auth)


def extract_owner_repo(url: str):
    pattern = r'https://github.com/([^/]+)/([^/]+)'
    match = re.match(pattern, url)
    if match:
        return match.group(1), match.group(2)
    else:
        return None, None

def get_github_repo_chunks(owner: str, repo_name: str, branch: str = 'main'):
    repo = g.get_repo(f"{owner}/{repo_name}")
    tree = repo.get_git_tree(branch, recursive=True)
    paths = []
    if tree.truncated:
        def traverse(path=""):
            for item in repo.get_contents(path, ref=branch):
                if item.type == "dir":
                    traverse(item.path)
                else:
                    paths.append(item.path)

        traverse()
    else:
        paths = [item.path for item in tree.tree if item.type == "blob"]

    def fetch_and_chunk(repo_path: str) -> list[dict] | None:
        path_lower = repo_path.lower()
        if Path(repo_path).suffix not in SUPPORTED_EXTENSIONS:
            return None
        if any(pat in path_lower for pat in SKIP_PATTERNS):
            return None
        file_contents = repo.get_contents(repo_path, ref=branch)
        all_contents = file_contents if isinstance(file_contents, list) else [file_contents]
        chunks = []
        for item in all_contents:
            if item.content is None:
                continue
            code = base64.b64decode(item.content).decode('utf-8', errors='ignore')

            ext = Path(repo_path).suffix
            file = {
                "path": repo_path,
                "content": code,
                "language": ext.lstrip('.'),
                "repo": repo,
                "branch": branch
            }

            chunks.extend(chunk_code_file(file))
        return chunks

    all_chunks = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_and_chunk, item): item for item in paths}
        for future in as_completed(futures):
            result = future.result()
            if result:
                all_chunks.extend(result)
    github_ingested.append({
        "owner": owner,
        'repo': repo
    })

    return all_chunks



def should_skip(file: dict) -> bool:
    path = file["path"].lower()
    if Path(file["path"]).suffix not in SUPPORTED_EXTENSIONS:
        return True
    if any(pat in path for pat in SKIP_PATTERNS):
        return True
    if len(file["content"].strip()) < 50:   # empty/trivial files
        return True
    return False














