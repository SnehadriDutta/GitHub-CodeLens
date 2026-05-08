from src.graphs.nodes import *
from src.structures.structure import RepoState
from langgraph.graph import StateGraph, END

def route_after_query(state: RepoState):    
    return state['category']

graph = StateGraph(RepoState)
graph.add_node('router', router)
graph.add_node('decline', decline)
graph.add_node('chunk_and_index', chunk_and_index)
graph.add_node('search_web',search_web)
graph.add_node('search_db',search_db)
graph.add_node('final_response',final_response)

graph.set_entry_point('router')
graph.add_conditional_edges(
    'router',
    route_after_query,{
        'coding': 'search_web',
        'repo_specific': 'chunk_and_index',
        'other': 'decline'
    }
)
graph.add_edge('search_web', 'final_response')
graph.add_edge('chunk_and_index', 'search_db')
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


def handle_query(query: str):
    state['query'] = query
    result = app.invoke(state)
    return result['response']





















