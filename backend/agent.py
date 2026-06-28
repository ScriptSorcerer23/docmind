"""
CrewAI agent — orchestrates retrieval decisions via direct Python tools.
LLM: gemini/gemini-2.5-flash (CrewAI native Gemini provider).
"""

import os
import re
import sys
import json
import logging
import asyncio
from typing import List, Tuple

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import google.generativeai as genai

def tool(name):
    def decorator(fn):
        fn.func = fn
        return fn
    return decorator

from config import GOOGLE_API_KEY, GROQ_API_KEY, supabase, embedder
from models import Source

# Configure Gemini client for helper tools
genai.configure(api_key=GOOGLE_API_KEY)
os.environ["GROQ_API_KEY"] = GROQ_API_KEY
logger = logging.getLogger(__name__)

# llama-3.1-8b-instant is deprecated by Groq (shutdown 08/16/26).
# Migrated to their recommended replacement: openai/gpt-oss-20b.
# See: https://console.groq.com/docs/deprecations
GROQ_MODEL = "groq/openai/gpt-oss-20b"


# ── Direct Agentic Tools ───────────────────────────────────────────

@tool("retrieve_documents")
def retrieve_documents(query: str, session_id: str, top_k: int = 5) -> str:
    """
    Search uploaded documents for relevant content, scoped to the caller's session.
    ALWAYS use this tool when the user asks about a specific person, their skills, experience,
    background, or any factual information that could be in an uploaded document.
    Do NOT answer questions about named individuals from general knowledge — always search documents first.
    """
    try:
        # Embed the query with Google text-embedding-004 (768-dim)
        query_embedding = embedder.embed_query(query)

        # Call Supabase RPC — cosine similarity search, scoped to this session only.
        # Threshold lowered from 0.5 to 0.4: a slightly noisy query (e.g. extracted
        # from a rambling message) can otherwise miss a real match entirely. Low
        # risk at small corpus sizes since there's little room for false positives.
        result = supabase.rpc(
            "match_documents",
            {
                "query_embedding": query_embedding,
                "match_threshold": 0.4,
                "match_count": top_k,
                "filter_session_id": session_id,
            },
        ).execute()

        chunks = result.data or []
        if not chunks:
            return "No relevant content found in uploaded documents."

        formatted = []
        for c in chunks:
            meta = c.get("metadata") or {}
            page = meta.get("page", "N/A") if isinstance(meta, dict) else "N/A"
            sim = c.get("similarity", 0)
            formatted.append(
                f"[Source: {c['filename']} | Page: {page} | "
                f"Similarity: {sim:.2f}]\n{c['content']}"
            )

        return "\n\n---\n\n".join(formatted)
    except Exception as e:
        logger.error("Error in retrieve_documents tool: %s", e)
        return f"Error retrieving documents: {str(e)}"


@tool("list_available_documents")
def list_available_documents(session_id: str, placeholder: str = None) -> str:
    """List documents uploaded in the caller's session. ALWAYS call this when the user asks what documents are available. The placeholder argument is unused — pass an empty string or omit it."""
    try:
        result = (
            supabase.table("documents")
            .select("filename, created_at")
            .eq("session_id", session_id)
            .order("created_at", desc=True)
            .execute()
        )
        docs = result.data or []
        if not docs:
            return "No documents uploaded yet."
        formatted = [f"- {d['filename']} (Uploaded: {d['created_at']})" for d in docs]
        return "Available documents:\n" + "\n".join(formatted)
    except Exception as e:
        logger.error("Error in list_available_documents tool: %s", e)
        return f"Error listing documents: {str(e)}"


@tool("summarize_document")
def summarize_document(filename: str, session_id: str) -> str:
    """Generate a summary of a specific document by its filename, within the caller's session."""
    try:
        # Find document id, scoped to this session
        doc_res = (
            supabase.table("documents")
            .select("id")
            .eq("filename", filename)
            .eq("session_id", session_id)
            .execute()
        )
        if not doc_res.data:
            return f"Document '{filename}' not found."
        
        doc_id = doc_res.data[0]["id"]
        
        # Get all chunks
        chunks_res = (
            supabase.table("document_chunks")
            .select("content, metadata")
            .eq("doc_id", doc_id)
            .execute()
        )
        chunks = chunks_res.data or []
        if not chunks:
            return f"Document '{filename}' has no content."
        
        # Sort chunks by chunk_index metadata
        def get_chunk_index(c):
            meta = c.get("metadata")
            if isinstance(meta, dict):
                return meta.get("chunk_index", 0)
            return 0
            
        sorted_chunks = sorted(chunks, key=get_chunk_index)
        full_text = "\n\n".join([c["content"] for c in sorted_chunks])
        
        prompt = (
            f"You are a Document Summarization AI. "
            f"Please generate a comprehensive summary of the following document content. "
            f"Highlight key points, findings, and structure. Do not invent facts.\n\n"
            f"Document Filename: {filename}\n\n"
            f"Content:\n{full_text}"
        )
        
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        logger.error("Error in summarize_document tool: %s", e)
        return f"Error summarizing document '{filename}': {str(e)}"


@tool("compare_documents")
def compare_documents(filenames: str, session_id: str) -> str:
    """Compare the contents, key points, or findings of two or more documents within the caller's session.
    The input should be a comma-separated string of filenames (e.g., 'report_q1.pdf, report_q2.pdf').
    """
    try:
        names = [n.strip() for n in filenames.split(",") if n.strip()]
        if len(names) < 2:
            return "Please provide at least two document filenames to compare."
            
        comparison_data = []
        for filename in names:
            doc_res = (
                supabase.table("documents")
                .select("id")
                .eq("filename", filename)
                .eq("session_id", session_id)
                .execute()
            )
            if not doc_res.data:
                return f"Document '{filename}' not found for comparison."
            doc_id = doc_res.data[0]["id"]
            
            chunks_res = (
                supabase.table("document_chunks")
                .select("content, metadata")
                .eq("doc_id", doc_id)
                .execute()
            )
            chunks = chunks_res.data or []
            
            def get_chunk_index(c):
                meta = c.get("metadata")
                if isinstance(meta, dict):
                    return meta.get("chunk_index", 0)
                return 0
            
            sorted_chunks = sorted(chunks, key=get_chunk_index)
            full_text = "\n\n".join([c["content"] for c in sorted_chunks])
            comparison_data.append((filename, full_text))
            
        prompt = (
            f"You are a Document Comparison AI. "
            f"Please perform a comparative analysis of the following {len(comparison_data)} documents. "
            f"Identify similarities, differences, contradictions, and key contrasts.\n\n"
        )
        for i, (fname, text) in enumerate(comparison_data, 1):
            prompt += f"Document {i}: {fname}\nContent Preview:\n{text[:10000]}\n\n---\n\n"
            
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        logger.error("Error in compare_documents tool: %s", e)
        return f"Error comparing documents: {str(e)}"


# ── Agent Kickoff ──────────────────────────────────────────────────

def get_crew_response(
    message: str,
    conversation_history: list,
    session_id: str,
    mcp_url: str = None,
) -> Tuple[str, List[Source]]:
    try:
        return _run_with_groq(message, conversation_history, session_id)
    except Exception as e:
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e) or "quota" in str(e).lower():
            print("Gemini quota hit — falling back to Groq")
            return _run_with_groq(message, conversation_history, session_id)
        raise


def _run_with_groq(
    message: str,
    conversation_history: list,
    session_id: str,
) -> Tuple[str, List[Source]]:
    """Run via Groq LLM (configured in GROQ_MODEL) using litellm, with a
    bounded agentic loop supporting chained/multi-step tool calls.
    Supports all four tools: retrieve_documents, list_available_documents,
    summarize_document, and compare_documents.
    """
    print("[GROQ] _run_with_groq executed")
    import litellm
    import json
    import re
    import time
    from models import Source

    def completion_with_retry(max_retries=3, base_delay=2.0, **kwargs):
        """Wrap litellm.completion with retry+backoff on transient rate limits.
        A 429 from Groq's free-tier TPM cap is common under bursty traffic and
        is not a real failure — retrying after a short wait usually succeeds.
        """
        last_err = None
        for attempt in range(max_retries):
            try:
                return litellm.completion(**kwargs)
            except litellm.exceptions.RateLimitError as e:
                last_err = e
                delay = base_delay * (2 ** attempt)  # 2s, 4s, 8s
                logger.warning(
                    "Groq rate limit hit (attempt %d/%d) — retrying in %.1fs",
                    attempt + 1, max_retries, delay,
                )
                time.sleep(delay)
        raise last_err

    tools = [
        {
            "type": "function",
            "function": {
                "name": "retrieve_documents",
                "description": "Search uploaded documents for relevant content. ALWAYS use this when the user asks about a specific person, their skills, experience, or any document-specific information.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The search query"},
                        "top_k": {"type": "integer", "description": "Number of results", "default": 5}
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "list_available_documents",
                "description": "List all uploaded documents in the knowledge base. Use this when the user asks what documents/files are available or uploaded.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "summarize_document",
                "description": "Generate a summary of a specific uploaded document, identified by its exact filename.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string", "description": "The exact filename of the document to summarize"}
                    },
                    "required": ["filename"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "compare_documents",
                "description": "Compare the contents of two or more uploaded documents.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filenames": {
                            "type": "string",
                            "description": "Comma-separated list of exact filenames to compare, e.g. 'report_q1.pdf, report_q2.pdf'"
                        }
                    },
                    "required": ["filenames"]
                }
            }
        }
    ]

    messages = [
        {
            "role": "system",
            "content": (
                "You are a Document Intelligence Analyst with four tools: "
                "retrieve_documents, list_available_documents, summarize_document, and compare_documents.\n"
                "- For ANY question about a person's skills, experience, background, education, or work, "
                "or any factual question that could be answered by an uploaded document — "
                "ALWAYS call retrieve_documents first. Never answer from general knowledge about people.\n"
                "- If the user asks what documents/files are available or uploaded — call list_available_documents.\n"
                "- If the user asks to summarize a specific document — call summarize_document with its filename.\n"
                "- If the user asks to compare two or more documents — call compare_documents with a "
                "comma-separated list of filenames.\n"
                "- For greetings and pure general knowledge (capitals, math, definitions) — answer directly without tools.\n"
                "When you use retrieved content, cite the source filename and page number in your answer.\n"
                "CRITICAL: When a tool returns specific information (filenames, dates, content), you MUST include "
                "those exact specifics in your final answer to the user. Never reply with a vague summary like "
                "'these are the available documents' without actually naming them. If list_available_documents "
                "returns a list of filenames, list every one of those filenames by name in your reply.\n"
                "QUERY EXTRACTION: when calling retrieve_documents, the `query` argument must be a short, clean "
                "search phrase containing only the core subject and what's being asked about — strip out greetings, "
                "small talk, filler, or unrelated context the user included before/after the actual question. "
                "For example, if the user says 'so work has been crazy lately, anyway quick question, what's the "
                "budget for Project Phoenix, let me know whenever', the query should be 'Project Phoenix budget', "
                "not the full sentence. A noisy query produces a worse embedding match and can cause real answers "
                "to be missed."
            )
        }
    ]
    for item in conversation_history:
        role = item.get("role") or "user"
        content = item.get("content") or ""
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    MAX_TOOL_ITERATIONS = 5  # safety cap against runaway/looping tool calls

    sources = []
    for iteration in range(MAX_TOOL_ITERATIONS):
        response = completion_with_retry(
            model=GROQ_MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.0
        )

        response_message = response.choices[0].message
        tool_calls = getattr(response_message, "tool_calls", None)

        if not tool_calls:
            # Model is done reasoning/calling tools — this is the final answer.
            return response_message.content, sources

        messages.append(response_message)

        for tool_call in tool_calls:
            fn_name = tool_call.function.name
            try:
                args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                args = {}

            if fn_name == "retrieve_documents":
                query = args.get("query")
                top_k = args.get("top_k", 5)
                fn = getattr(retrieve_documents, "func", retrieve_documents)
                tool_result = fn(query=query, top_k=top_k, session_id=session_id)

                # Parse sources from the tool result
                source_pattern = re.compile(
                    r"\[Source:\s*(.+?)\s*\|\s*Page:\s*(\S+)\s*\|\s*Similarity:\s*([\d.]+)\]"
                )
                for m in source_pattern.finditer(tool_result):
                    page_val = m.group(2)
                    sources.append(
                        Source(
                            filename=m.group(1).strip(),
                            chunk_preview="",
                            page=int(page_val) if page_val.isdigit() else None,
                            similarity=float(m.group(3)),
                        )
                    )

            elif fn_name == "list_available_documents":
                fn = getattr(list_available_documents, "func", list_available_documents)
                tool_result = fn(session_id=session_id)

            elif fn_name == "summarize_document":
                filename = args.get("filename", "")
                fn = getattr(summarize_document, "func", summarize_document)
                tool_result = fn(filename=filename, session_id=session_id)

            elif fn_name == "compare_documents":
                filenames = args.get("filenames", "")
                fn = getattr(compare_documents, "func", compare_documents)
                tool_result = fn(filenames=filenames, session_id=session_id)

            else:
                tool_result = f"Unknown tool: {fn_name}"

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": fn_name,
                "content": tool_result
            })

        # Loop back: give the model the new tool results and let it decide
        # whether it needs another tool call or is ready to answer.

    # Safety net: hit MAX_TOOL_ITERATIONS without a final answer. Force one
    # last call with tool_choice="none" so the model must respond in text
    # using whatever it has gathered so far, rather than failing the request.
    logger.warning("Hit MAX_TOOL_ITERATIONS (%d) without a final answer — forcing text response.", MAX_TOOL_ITERATIONS)
    final_response = completion_with_retry(
        model=GROQ_MODEL,
        messages=messages,
        tools=tools,
        tool_choice="none",
        temperature=0.0
    )
    return final_response.choices[0].message.content, sources


def _stream_with_groq(
    message: str,
    conversation_history: list,
    session_id: str,
):
    """Generator variant of _run_with_groq that yields SSE-ready event dicts
    as the agentic loop runs, then yields a final 'done' event.

    Yields dicts matching one of these shapes:
      {"type": "tool_call",   "tool": <name>, "args": <client-safe args>}
      {"type": "tool_result", "tool": <name>, "summary": <short human text>}
      {"type": "done",        "answer": <str>, "sources": [<Source.dict()>...]}
      {"type": "error",       "message": <user-safe str>}

    IMPORTANT: session_id is NEVER included in any yielded event — it is only
    used server-side to scope tool calls, identical to _run_with_groq.
    """
    import litellm
    import json as _json
    import re as _re
    import time
    from models import Source

    # ── shared retry helper (identical to the one inside _run_with_groq) ──
    def completion_with_retry(max_retries=3, base_delay=2.0, **kwargs):
        last_err = None
        for attempt in range(max_retries):
            try:
                return litellm.completion(**kwargs)
            except litellm.exceptions.RateLimitError as e:
                last_err = e
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "[stream] Groq rate limit (attempt %d/%d) — retrying in %.1fs",
                    attempt + 1, max_retries, delay,
                )
                time.sleep(delay)
        raise last_err

    # ── tool schema (identical to _run_with_groq) ─────────────────────────
    tools = [
        {
            "type": "function",
            "function": {
                "name": "retrieve_documents",
                "description": "Search uploaded documents for relevant content. ALWAYS use this when the user asks about a specific person, their skills, experience, or any document-specific information.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The search query"},
                        "top_k": {"type": "integer", "description": "Number of results", "default": 5}
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "list_available_documents",
                "description": "List all uploaded documents in the knowledge base. Use this when the user asks what documents/files are available or uploaded.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "summarize_document",
                "description": "Generate a summary of a specific uploaded document, identified by its exact filename.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string", "description": "The exact filename of the document to summarize"}
                    },
                    "required": ["filename"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "compare_documents",
                "description": "Compare the contents of two or more uploaded documents.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filenames": {
                            "type": "string",
                            "description": "Comma-separated list of exact filenames to compare, e.g. 'report_q1.pdf, report_q2.pdf'"
                        }
                    },
                    "required": ["filenames"]
                }
            }
        }
    ]

    # ── system prompt + history (identical to _run_with_groq) ────────────
    messages = [
        {
            "role": "system",
            "content": (
                "You are a Document Intelligence Analyst with four tools: "
                "retrieve_documents, list_available_documents, summarize_document, and compare_documents.\n"
                "- For ANY question about a person's skills, experience, background, education, or work, "
                "or any factual question that could be answered by an uploaded document — "
                "ALWAYS call retrieve_documents first. Never answer from general knowledge about people.\n"
                "- If the user asks what documents/files are available or uploaded — call list_available_documents.\n"
                "- If the user asks to summarize a specific document — call summarize_document with its filename.\n"
                "- If the user asks to compare two or more documents — call compare_documents with a "
                "comma-separated list of filenames.\n"
                "- For greetings and pure general knowledge (capitals, math, definitions) — answer directly without tools.\n"
                "When you use retrieved content, cite the source filename and page number in your answer.\n"
                "CRITICAL: When a tool returns specific information (filenames, dates, content), you MUST include "
                "those exact specifics in your final answer to the user. Never reply with a vague summary like "
                "'these are the available documents' without actually naming them. If list_available_documents "
                "returns a list of filenames, list every one of those filenames by name in your reply.\n"
                "QUERY EXTRACTION: when calling retrieve_documents, the `query` argument must be a short, clean "
                "search phrase containing only the core subject and what's being asked about — strip out greetings, "
                "small talk, filler, or unrelated context the user included before/after the actual question. "
                "For example, if the user says 'so work has been crazy lately, anyway quick question, what's the "
                "budget for Project Phoenix, let me know whenever', the query should be 'Project Phoenix budget', "
                "not the full sentence. A noisy query produces a worse embedding match and can cause real answers "
                "to be missed."
            )
        }
    ]
    for item in conversation_history:
        role = item.get("role") or "user"
        content = item.get("content") or ""
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    MAX_TOOL_ITERATIONS = 5
    sources = []

    try:
        for iteration in range(MAX_TOOL_ITERATIONS):
            response = completion_with_retry(
                model=GROQ_MODEL,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=0.0
            )

            response_message = response.choices[0].message
            tool_calls = getattr(response_message, "tool_calls", None)

            if not tool_calls:
                # Final answer — no more tool calls.
                yield {
                    "type": "done",
                    "answer": response_message.content,
                    "sources": [s.dict() for s in sources],
                }
                return

            messages.append(response_message)

            for tool_call in tool_calls:
                fn_name = tool_call.function.name
                try:
                    args = _json.loads(tool_call.function.arguments)
                except _json.JSONDecodeError:
                    args = {}

                # Build client-safe args: never include session_id.
                client_args = {k: v for k, v in args.items() if k != "session_id"}

                # ── emit: tool about to run ───────────────────────────────
                yield {"type": "tool_call", "tool": fn_name, "args": client_args}

                # ── dispatch (identical session-scoping as _run_with_groq) ─
                if fn_name == "retrieve_documents":
                    query = args.get("query")
                    top_k = args.get("top_k", 5)
                    fn = getattr(retrieve_documents, "func", retrieve_documents)
                    tool_result = fn(query=query, top_k=top_k, session_id=session_id)

                    # Parse sources
                    source_pattern = _re.compile(
                        r"\[Source:\s*(.+?)\s*\|\s*Page:\s*(\S+)\s*\|\s*Similarity:\s*([\d.]+)\]"
                    )
                    chunk_count = 0
                    for m in source_pattern.finditer(tool_result):
                        page_val = m.group(2)
                        sources.append(
                            Source(
                                filename=m.group(1).strip(),
                                chunk_preview="",
                                page=int(page_val) if page_val.isdigit() else None,
                                similarity=float(m.group(3)),
                            )
                        )
                        chunk_count += 1
                    if "No relevant content" in tool_result:
                        summary = "No relevant content found"
                    else:
                        summary = f"Found {chunk_count} relevant chunk{'s' if chunk_count != 1 else ''}"

                elif fn_name == "list_available_documents":
                    fn = getattr(list_available_documents, "func", list_available_documents)
                    tool_result = fn(session_id=session_id)
                    if "No documents" in tool_result:
                        summary = "No documents uploaded yet"
                    else:
                        doc_count = tool_result.count("\n- ") + (1 if "- " in tool_result else 0)
                        summary = f"Found {doc_count} document{'s' if doc_count != 1 else ''}"

                elif fn_name == "summarize_document":
                    filename = args.get("filename", "")
                    fn = getattr(summarize_document, "func", summarize_document)
                    tool_result = fn(filename=filename, session_id=session_id)
                    if "not found" in tool_result.lower() or "error" in tool_result.lower():
                        summary = f"Could not summarize '{filename}'"
                    else:
                        summary = "Summary generated"

                elif fn_name == "compare_documents":
                    filenames = args.get("filenames", "")
                    fn = getattr(compare_documents, "func", compare_documents)
                    tool_result = fn(filenames=filenames, session_id=session_id)
                    if "not found" in tool_result.lower() or "error" in tool_result.lower():
                        summary = "Could not compare documents"
                    else:
                        summary = "Comparison complete"

                else:
                    tool_result = f"Unknown tool: {fn_name}"
                    summary = f"Unknown tool: {fn_name}"

                # ── emit: tool finished ───────────────────────────────────
                yield {"type": "tool_result", "tool": fn_name, "summary": summary}

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": fn_name,
                    "content": tool_result,
                })

        # Hit MAX_TOOL_ITERATIONS — force a final text response.
        logger.warning("[stream] Hit MAX_TOOL_ITERATIONS (%d) — forcing text response.", MAX_TOOL_ITERATIONS)
        final_response = completion_with_retry(
            model=GROQ_MODEL,
            messages=messages,
            tools=tools,
            tool_choice="none",
            temperature=0.0
        )
        yield {
            "type": "done",
            "answer": final_response.choices[0].message.content,
            "sources": [s.dict() for s in sources],
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        error_str = str(e)
        if "429" in error_str or "quota" in error_str.lower() or "RESOURCE_EXHAUSTED" in error_str:
            user_msg = "I'm a bit overwhelmed right now — too many requests at once. Please wait a moment and try again."
        elif "timeout" in error_str.lower():
            user_msg = "That took too long to process. Please try again."
        elif "connect" in error_str.lower() or "connection" in error_str.lower():
            user_msg = "I'm having trouble connecting to my services. Please check your internet connection and try again."
        else:
            user_msg = "Something went wrong on my end. Please try again in a moment."
        yield {"type": "error", "message": user_msg}


def _run_crew(
    message: str,
    conversation_history: list,
    llm,
) -> Tuple[str, List[Source]]:
    if isinstance(llm, str) and "groq" in llm.lower() or not isinstance(llm, str):
        print("[GROQ] _run_crew executed")
    else:
        print("[GEMINI] _run_crew executed")
        
    tools = [retrieve_documents, list_available_documents, summarize_document, compare_documents]

    analyst = Agent(
        role="Document Intelligence Analyst",
        goal=(
            "Answer user questions accurately using the available tools.\n"
            "IMPORTANT RULES:\n"
            "- For ANY question about a person's skills, experience, background, education, or work — "
            "ALWAYS call retrieve_documents first. Never answer from general knowledge about people.\n"
            "- For questions about what documents exist — call list_available_documents.\n"
            "- For summarization requests — call list_available_documents then summarize_document.\n"
            "- ONLY skip tools for greetings and pure general knowledge questions (capitals, math, definitions)."
        ),
        backstory=(
            "You are an expert at analyzing uploaded documents and "
            "providing grounded, cited answers. You are selective about "
            "when to retrieve — you do not retrieve unnecessarily."
        ),
        tools=tools,
        verbose=True,
        llm=llm,
    )

    history_str = (
        json.dumps(conversation_history, indent=2)
        if conversation_history
        else "[]"
    )

    task = Task(
        description=f"""
Conversation history:
{history_str}

Current user message: {message}

Instructions:
- If the user asks general greetings or conversational questions, respond directly.
- If they ask what files are uploaded, use list_available_documents.
- If they want to summarize a file, use summarize_document.
- If they want to compare files, use compare_documents.
- If the question is factual about document contents, call retrieve_documents.
- When you use retrieved content, always cite the source filename and page number.
- Format your response clearly.
- At the end of your response, if you used sources, list them in this exact format:
  SOURCES_JSON: [{{"filename": "...", "chunk_preview": "...", "page": N, "similarity": 0.XX}}]
""",
        expected_output=(
            "A clear answer to the user's question. If documents were "
            "retrieved, include source citations (filename, page). "
            "If no retrieval was needed, answer directly."
        ),
        agent=analyst,
    )

    crew = Crew(agents=[analyst], tasks=[task], verbose=False)
    result = crew.kickoff()

    raw_output = str(result)
    answer, sources = _parse_sources(raw_output)
    return answer, sources


def _parse_sources(raw_output: str) -> Tuple[str, List[Source]]:
    """Extract structured sources from agent output if present."""
    sources: List[Source] = []

    # Try SOURCES_JSON marker first
    match = re.search(r"SOURCES_JSON:\s*(\[.*?\])", raw_output, re.DOTALL)
    if match:
        try:
            raw_sources = json.loads(match.group(1))
            sources = [Source(**s) for s in raw_sources]
            answer = raw_output[: match.start()].strip()
            return answer, sources
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("Failed to parse SOURCES_JSON: %s", e)

    # Fallback: extract [Source: ...] lines
    source_pattern = re.compile(
        r"\[Source:\s*(.+?)\s*\|\s*Page:\s*(\S+)\s*\|\s*Similarity:\s*([\d.]+)\]"
    )
    for m in source_pattern.finditer(raw_output):
        sources.append(
            Source(
                filename=m.group(1).strip(),
                chunk_preview="",
                page=int(m.group(2)) if m.group(2).isdigit() else None,
                similarity=float(m.group(3)),
            )
        )

    return raw_output, sources