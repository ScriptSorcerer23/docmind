"""
CrewAI agent — orchestrates retrieval decisions via MCP tool.
The agent decides whether to call retrieve_documents or answer directly.
"""

import re
import json
from typing import List

from crewai import Agent, Task, Crew
from crewai_tools import MCPServerAdapter

from models import Source


def get_crew_response(message: str, conversation_history: list, mcp_url: str = "http://localhost:8000/mcp/sse"):
    """
    Run the CrewAI agent with the user's message.

    Returns:
        (answer: str, sources: List[Source])
    """
    # Connect to MCP server
    with MCPServerAdapter(
        server_params={"url": mcp_url, "transport": "sse"}
    ) as mcp_adapter:
        tools = mcp_adapter.tools  # exposes retrieve_documents as a CrewAI tool

        analyst = Agent(
            role="Document Intelligence Analyst",
            goal=(
                "Answer user questions accurately. Use the retrieve_documents tool "
                "only when the question requires document-specific knowledge. For "
                "greetings, general questions, or conversational turns, answer "
                "directly without retrieval."
            ),
            backstory=(
                "You are an expert at analyzing uploaded documents and providing "
                "grounded, cited answers. You are selective about when to retrieve — "
                "you do not retrieve unnecessarily."
            ),
            tools=tools,
            verbose=True,
            llm="gpt-4o-mini",
        )

        history_str = json.dumps(conversation_history, indent=2) if conversation_history else "[]"

        task = Task(
            description=f"""
Conversation history:
{history_str}

Current user message: {message}

Instructions:
- If the question is factual and likely requires document context, call retrieve_documents.
- If the question is general, conversational, or answerable without documents, respond directly.
- When you use retrieved content, always cite the source filename and page number.
- Format your response clearly.
- At the end of your response, if you used sources, list them in this exact format:
  SOURCES_JSON: [{{"filename": "...", "chunk_preview": "...", "page": N, "similarity": 0.XX}}]
""",
            expected_output=(
                "A clear answer to the user's question. If documents were retrieved, "
                "include source citations (filename, page). If no retrieval was needed, "
                "state that directly."
            ),
            agent=analyst,
        )

        crew = Crew(agents=[analyst], tasks=[task], verbose=False)
        result = crew.kickoff()

    # Parse answer and sources
    raw_output = str(result)
    answer, sources = _parse_sources(raw_output)
    return answer, sources


def _parse_sources(raw_output: str) -> tuple[str, List[Source]]:
    """Extract structured sources from agent output if present."""
    sources = []

    # Look for SOURCES_JSON marker
    match = re.search(r"SOURCES_JSON:\s*(\[.*?\])", raw_output, re.DOTALL)
    if match:
        try:
            raw_sources = json.loads(match.group(1))
            sources = [Source(**s) for s in raw_sources]
            # Remove the SOURCES_JSON line from the answer
            answer = raw_output[: match.start()].strip()
        except (json.JSONDecodeError, Exception):
            answer = raw_output
    else:
        answer = raw_output

    return answer, sources
