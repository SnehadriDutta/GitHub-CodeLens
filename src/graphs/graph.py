import time
from src.graphs.nodes import *
from src.utils.structure import RepoState
from langgraph.graph import StateGraph, END
from fastapi.responses import JSONResponse
from src.utils.log import logger

def route_after_query(state: RepoState):    
    return state['category']

graph = StateGraph(RepoState)
graph.add_node('router', router)
graph.add_node('decline', decline)
graph.add_node('search_web',search_web)
graph.add_node('search_db',search_db)
graph.add_node('final_response',final_response)

graph.set_entry_point('router')
graph.add_conditional_edges(
    'router',
    route_after_query,{
        'coding': 'search_web',
        'repo_specific': 'search_db',
        'other': 'decline'
    }
)
graph.add_edge('search_web', 'final_response')
graph.add_edge('search_db', 'final_response')
graph.add_edge('final_response', END)
graph.add_edge('decline', END)

app = graph.compile()
state: RepoState = {
        "query": "",
        "category": "",
        "repo_link": "",
        "web_results": [],
        "retrieved_chunks": [],
        "response": "",
        "messages": [],
}

def handle_query(query: str, github_link: str):
    state['query'] = query
    state['repo_link'] = github_link
    result = app.invoke(state)
    return result['response']

async def ingest_and_save_repo(github_link: str) -> JSONResponse:
    owner, repo = github_fetcher.extract_owner_repo(github_link)
    if owner and repo:
        if not db_processing.check_repo_present_in_db(owner=owner, repo=repo):
            t0 = time.time()
            #chunks = github_fetcher.get_github_repo_chunks(owner=owner, repo_name=repo)
            chunks = await github_fetcher.get_github_repo_chunks_aiohttp(owner=owner, repo_name=repo)
            logger.debug(f"Fetch: {time.time() - t0:.2f}s, chunks: {len(chunks)}")

            t1 = time.time()
            db_processing.save_to_db(owner=owner, repo=repo, chunks=chunks)
            logger.debug(f"Save to DB: {time.time() - t1:.2f}s")
        github_fetcher.github_ingested.append({
            "owner": owner,
            'repo': repo
        })
        return JSONResponse(
            status_code=200,
            content={'message' : "Github repo read and saved!!"}
        )
    else:
        return JSONResponse(
            status_code=404,
            content={'message' : "Github Repo not found"}
        )


















