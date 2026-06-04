"""
MCP server — exposes `retrieve_documents` as an agent-callable tool.
Uses SSE transport so it runs in-process with FastAPI (no subprocess).
"""

from mcp.server import Server
from mcp.types import Tool, TextContent

from config import supabase, embedder

server = Server("rag-retrieval-server")


@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="retrieve_documents",
            description=(
                "Search uploaded documents for content relevant to a query. "
                "Use when the user asks a factual question that likely requires "
                "document context. Do NOT use for greetings, general knowledge "
                "questions, or conversational turns."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to run against uploaded documents",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of chunks to retrieve (default 5)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name != "retrieve_documents":
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    query = arguments["query"]
    top_k = arguments.get("top_k", 5)

    # Embed the query
    query_embedding = embedder.embed_query(query)

    # Call Supabase RPC — cosine similarity search
    result = supabase.rpc(
        "match_documents",
        {
            "query_embedding": query_embedding,
            "match_threshold": 0.7,
            "match_count": top_k,
        },
    ).execute()

    chunks = result.data or []
    if not chunks:
        return [
            TextContent(
                type="text",
                text="No relevant content found in uploaded documents.",
            )
        ]

    formatted = []
    for c in chunks:
        page = c.get("metadata", {}).get("page", "N/A") if isinstance(c.get("metadata"), dict) else "N/A"
        formatted.append(
            f"[Source: {c['filename']} | Page: {page} | "
            f"Similarity: {c['similarity']:.2f}]\n{c['content']}"
        )

    return [TextContent(type="text", text="\n\n---\n\n".join(formatted))]
