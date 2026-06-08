import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  timeout: 300_000, // 5 min — agent can be slow
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
