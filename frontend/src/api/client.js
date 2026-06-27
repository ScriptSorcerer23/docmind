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