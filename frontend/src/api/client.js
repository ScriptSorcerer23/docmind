/**
 * API client — Axios wrappers for all backend endpoints.
 */
import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
  timeout: 120000, // 2 min timeout for agent responses
});

/**
 * Upload a PDF or TXT file.
 * @param {File} file
 * @param {function} onProgress - progress callback (0-100)
 * @returns {Promise<{doc_id, filename, chunk_count}>}
 */
export const uploadDocument = (file, onProgress) => {
  const form = new FormData();
  form.append('file', file);
  return api.post('/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (e) => {
      if (onProgress && e.total) {
        onProgress(Math.round((e.loaded * 100) / e.total));
      }
    },
  });
};

/**
 * Get list of all uploaded documents.
 * @returns {Promise<Array<{id, filename, created_at}>>}
 */
export const getDocuments = () => api.get('/documents');

/**
 * Delete a document by ID (cascades to chunks).
 * @param {string} id
 */
export const deleteDocument = (id) => api.delete(`/documents/${id}`);

/**
 * Send a chat message to the CrewAI agent.
 * @param {string} message
 * @param {Array} history - conversation history
 * @returns {Promise<{answer, sources}>}
 */
export const sendMessage = (message, history) =>
  api.post('/chat', { message, conversation_history: history });
