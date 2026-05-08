import re
from datetime import datetime
from typing import List, Any
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, SparseVectorParams, Distance, Modifier, SparseVector, PointStruct
from qdrant_client.models import Filter, FieldCondition, MatchValue, Prefetch, Fusion, FusionQuery
from fastembed import TextEmbedding, SparseTextEmbedding
from sentence_transformers import CrossEncoder
from dotenv import load_dotenv
load_dotenv(override=True)


COLLECTION_NAME="codebase"
DENSE_EMBEDDING_MODEL="sentence-transformers/all-MiniLM-L6-v2"
SPARSE_EMBEDDING_MODEL = "Qdrant/bm25"
CROSSENCODER_EMBEDDING_MODEL = 'cross-encoder/ms-marco-MiniLM-L-6-v2'

dense_model = TextEmbedding(DENSE_EMBEDDING_MODEL)
sparse_model = SparseTextEmbedding(SPARSE_EMBEDDING_MODEL)
reranker = CrossEncoder(CROSSENCODER_EMBEDDING_MODEL)

path="./qdrant_data"
client = QdrantClient(path=path)
collections = [c.name for c in client.get_collections().collections]

if COLLECTION_NAME not in collections:
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            'dense': VectorParams(size=384,
                                    distance=Distance.COSINE)
        },
        sparse_vectors_config={
            'sparse': SparseVectorParams(modifier=Modifier.IDF) #IDF weighting = BM25
        }
    )

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

def save_to_db(owner: str, repo:str,chunks:List[Any]):
    points = []
    for chunk in chunks:
        dense_vec, sparse_vec = embed(chunk['text'])
        point = PointStruct(
            id=get_ticks(),
            vector={'dense': dense_vec, 'sparse': sparse_vec},
            payload={**chunk, 'owner': owner, 'repo': repo, }
        )
        points.append(point)
    client.upsert(
        collection_name=COLLECTION_NAME,
        points=points
    )

def query_db(query: str, repo_url: str, limit: int = 5):
    dense_vec, sparse_vec = embed(query)
    owner, repo = extract_owner_repo(repo_url)

    reranked = []
    if owner and repo:
        query_filter = Filter(
            must=[
                FieldCondition(key="owner", match=MatchValue(value=owner)),
                FieldCondition(key="repo", match=MatchValue(value=repo))
            ]
        )
        results = client.query_points(
            collection_name=COLLECTION_NAME,
            prefetch=[
                Prefetch(query=dense_vec, using='dense', filter=query_filter, limit=20),
                Prefetch(query=sparse_vec, using='sparse', filter=query_filter, limit=20)
            ],
            query=FusionQuery(fusion=Fusion.RRF),
            with_payload=True,
            limit=20
        )

        points = results.points
        pairs = [(query, p.payload) for p in points]
        scores = reranker.predict(pairs)
        reranked = sorted(zip(scores, points), key=lambda x: x[0], reverse=True)[:limit]

    return reranked

def get_ticks():
    dt = datetime.now()
    epoch = datetime(1, 1, 1)
    return int((dt - epoch).total_seconds() * 10**7)

def embed(text: str):
    dense = list(dense_model.embed([text]))[0].tolist()
    sp = list(sparse_model.embed(documents=[text]))[0]
    sparse = SparseVector(indices=sp.indices.tolist(), values=sp.values.tolist())
    return dense, sparse

def extract_owner_repo(url: str):
    pattern = r'https://github.com/([^/]+)/([^/]+)'
    match = re.match(pattern, url)
    if match:
        return match.group(1), match.group(2)
    else:
        return None, None









