import os
from dotenv import load_dotenv
from tavily import TavilyClient
load_dotenv(override=True)

TAVILY_API_KEY=os.getenv('TAVILY_API_KEY')
tavily_client = TavilyClient(api_key=TAVILY_API_KEY)


def search_web(query: str):
    tavily_response = tavily_client.search(
        query=query,
        # include_domains=["github.com", "stackoverflow.com"]
        search_depth="advanced",
        time_range="week",
        chunks_per_source=5
    )
    return tavily_response













