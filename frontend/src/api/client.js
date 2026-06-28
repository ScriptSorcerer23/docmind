import axios from 'axios';

// Generate a session id once per browser tab session.
// sessionStorage clears automatically when the tab is closed — this is just a
// convenient place to keep it client-side; it is NOT the actual cleanup
// mechanism. Real cleanup is a server-side cron job that deletes any
// document older than 1 hour, regardless of whether the tab is still open.
function getSessionId() {
  let sessionId = sessionStorage.getItem('docmind_session_id');
  if (!sessionId) {
    sessionId = crypto.randomUUID();
    sessionStorage.setItem('docmind_session_id', sessionId);
  }
  return sessionId;
}

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  timeout: 300_000, // 5 min — agent can be slow
});

// Attach the session id to every outgoing request automatically.
api.interceptors.request.use((config) => {
  config.headers['X-Session-Id'] = getSessionId();
  return config;
});

export async function uploadDocument(file, onProgress) {
  const form = new FormData();
  form.append('file', file);
  return api.post('/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (e) => {
      if (onProgress && e.total) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    },
  });
}

export async function getDocuments() {
  return api.get('/documents');
}

export async function deleteDocument(id) {
  return api.delete(`/documents/${id}`);
}

export async function sendMessage(message, conversationHistory = []) {
  return api.post('/chat', {
    message,
    conversation_history: conversationHistory,
  });
}

/**
 * Stream real-time agent progress from /chat/stream via SSE.
 *
 * EventSource doesn't support custom headers, so we use fetch + ReadableStream
 * to parse the `data: {...}\n\n` frames manually and forward them to callbacks.
 *
 * @param {string} message
 * @param {Array}  conversationHistory
 * @param {{ onEvent: (event: object) => void, signal?: AbortSignal }} options
 *   - onEvent is called for every parsed SSE event object
 *   - signal  is an optional AbortSignal to cancel mid-stream
 */
export async function streamMessage(message, conversationHistory = [], { onEvent, signal } = {}) {
  const baseURL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
  const sessionId = getSessionId();

  const response = await fetch(`${baseURL}/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Session-Id': sessionId,
    },
    body: JSON.stringify({ message, conversation_history: conversationHistory }),
    signal,
  });

  if (!response.ok) {
    // Try to surface a detail message from the JSON body if available.
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      detail = body?.detail || detail;
    } catch (_) { /* ignore */ }
    throw new Error(detail);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  // eslint-disable-next-line no-constant-condition
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // SSE frames are delimited by double newlines.
    const frames = buffer.split('\n\n');
    // Keep the last (possibly incomplete) chunk in the buffer.
    buffer = frames.pop();

    for (const frame of frames) {
      // Each frame may have multiple lines; find the `data:` line.
      for (const line of frame.split('\n')) {
        if (line.startsWith('data:')) {
          const jsonStr = line.slice('data:'.length).trim();
          if (!jsonStr) continue;
          try {
            const event = JSON.parse(jsonStr);
            onEvent?.(event);
          } catch (_) {
            console.warn('[streamMessage] Failed to parse SSE frame:', jsonStr);
          }
        }
      }
    }
  }
}