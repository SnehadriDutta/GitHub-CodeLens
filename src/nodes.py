import json
import os
from langchain_groq import ChatGroq
from dotenv import load_dotenv
from src.structure import RepoState, ProcessQueryResponse
from src.workflow import WorkFlow

load_dotenv(override=True)

GROQ_API_KEY=os.getenv('GROQ_API_KEY')

router_llm = ChatGroq(
    api_key=GROQ_API_KEY,
    model="llama-3.1-8b-instant",
    temperature=0.5,
    max_tokens=1024
)

synthesizer_llm = ChatGroq(
    api_key=GROQ_API_KEY,
    model="openai/gpt-oss-20b",
    temperature=0.5,
    max_tokens=1024
)

router_prompt = """
You are a query classifier. Classify the input query into exactly one category.

CATEGORIES:

1. "repo_specific"
   REQUIRED: query must contain a valid GitHub URL (https://github.com/<user>/<repo>)
   AND asks anything about that repo (explain, fix, add feature, review, etc.)
   Example: "explain the auth flow https://github.com/org/project"

2. "coding"
   ANY query that involves:
   - Writing, fixing, reviewing, or explaining code
   - Programming languages, frameworks, libraries, tools, APIs
   - Algorithms, data structures, system design
   - Errors, stack traces, debugging
   - DevOps, CI/CD, databases, networking (technical)
   - Vague but clearly technical: "websocket code", "redis setup", "fix this loop"
   Examples: "code for websocket", "why is my async function broken", "how does JWT work", "write a bash script"

3. "other"
   ONLY if the query has zero relation to software, coding, or technology.
   Examples: "what's the weather", "write me a poem", "history of Rome"

DECISION RULES:
- If a GitHub URL exists → "repo_specific" (always)
- If the query has ANY technical/coding intent → "coding" (even if vague or one word)
- "other" is the last resort — only for clearly non-technical queries
- Use conversation history ONLY to resolve ambiguous follow-ups (e.g., "fix it" after a coding discussion → "coding")

Query: {query}
History: {history}
"""

decline_prompt = """
Decline the query of the user politely. 
Tell the user that we do not process whatever the user has asked, stating that we are here to help with coding.
Query: {query}
"""

web_query_prompt="""
You are an expert coding assistant. Answer the user's query using the web search results and conversation history.

Rules:
- Prioritize web results as the factual source
- Maintain continuity with history (same stack, constraints, prior decisions)
- Provide working code with inline comments explaining non-obvious logic
- Do not add explanation outside the code unless it cannot fit in a comment
- If web results are insufficient, state exactly what is missing

Current Query: {query}
History: {history}
Web Search Results: {web_results}

Respond in this structure:
### Solution
<brief 1-2 line problem restatement only if needed>

### Code
<complete working code with inline comments>

### Notes
<only critical warnings, edge cases, or missing info — omit if none>
"""

github_based_prompt="""
You are an expert coding assistant with full access to the user's repository.

Rules:
- Use repository chunks as the source of truth
- Always cite the source: file path, class name, and method name for every referenced component
- Recommend precise, minimal code changes consistent with existing style
- Do not assume or fabricate missing implementations
- If repo data is insufficient, state exactly what is missing

Current Query: {query}
History: {history}
Repository Chunks: {github_results}

Respond in this structure:
### Relevant Components
<File: path/to/file.py | Class: ClassName | Method: method_name>
<repeat for each relevant component>

### Solution
<complete working code with inline comments, referencing actual class/method names from above>

### Notes
<only critical warnings or missing context — omit if none>
"""

def router(state: RepoState):
    process_llm = router_llm.with_structured_output(ProcessQueryResponse)
    formatted_history = WorkFlow.format_history(state['messages'])
    result = process_llm.invoke(router_prompt.format(query=state["query"], history=formatted_history))
    print(state["query"] + " | "+result['category'])
    new_query = state["query"]
    repo_link = ""
    if result['category'] == 'repo_specific':
        new_query = result['query']
        repo_link = result['github_link']    
    return {**state, 'query': new_query, 'category': result['category'], 'repo_link': repo_link}

def decline(state: RepoState):
    response = router_llm.invoke(decline_prompt.format(query=state['query']))
    return {**state, 'response': response.content}

def chunk_and_index(state: RepoState):
    owner, repo = WorkFlow.extract_owner_repo(url=state['repo_link'])
    if owner and repo:
        if not WorkFlow.check_repo_present_in_db(owner=owner, repo=repo):
            all_files = WorkFlow.get_github_repo(owner=owner, repo=repo)
            chunks = WorkFlow.get_codebase_chunks(all_files)
            WorkFlow.save_to_db(owner=owner, repo=repo, chunks=chunks)
    return {**state}

def search_web(state: RepoState):
    web_results = []
    search_result = WorkFlow.search_web(state['query'])
    results = search_result.get('results', [])
    for item in results:
        web_results.append({
            "url": item.get('url', ''),
            "content": item.get('content', '')
        })
    return {**state, 'web_results': web_results}

def search_db(state: RepoState):
    db_result = WorkFlow.fetch_from_db(query=state['query'], repo_url=state['repo_link'])
    return {**state, 'retrieved_chunks': db_result}

def final_response(state: RepoState):
    response = ''
    history = state['messages']
    formatted_history = WorkFlow.format_history(history)
    if state['category'] == 'coding':
        response += synthesizer_llm.invoke(web_query_prompt.format(query=state['query'], web_results=json.dumps(state['web_results']), history=formatted_history)).content

    elif state['category'] == 'repo_specific':
        response += synthesizer_llm.invoke(github_based_prompt.format(query=state['query'], github_results=json.dumps(state['retrieved_chunks']), history=formatted_history)).content
    history.append({
        'role' : 'user',
        'content' : state['query']
    })
    history.append({
        'role': 'assistant',
        'content': response
    })
    return {**state, 'response': response, 'messages': history}




