import { useCallback, useEffect, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import toast from 'react-hot-toast';
import { uploadDocument, getDocuments, deleteDocument } from '../api/client';
import {
  IconSparkles,
  IconUpload,
  IconLoader,
  IconFolder,
  IconFilePdf,
  IconFileText,
  IconTrash,
} from './Icons';

export default function DocumentLibrary({ refreshKey, onUploadComplete }) {
  const [docs, setDocs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);

  /* ── Fetch documents ─────────────────────────── */
  const fetchDocs = async () => {
    try {
      const res = await getDocuments();
      setDocs(res.data || []);
    } catch {
      toast.error('Failed to load documents');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocs();
  }, [refreshKey]);

  /* ── Upload ──────────────────────────────────── */
  const onDrop = useCallback(async (accepted) => {
    if (!accepted.length) return;
    const file = accepted[0];
    const ext = file.name.split('.').pop().toLowerCase();
    if (!['pdf', 'txt'].includes(ext)) {
      toast.error('Only PDF and TXT files are supported');
      return;
    }

    setUploading(true);
    setProgress(0);
    try {
      const res = await uploadDocument(file, setProgress);
      toast.success(`${res.data.filename} — ${res.data.chunk_count} chunks indexed`);
      onUploadComplete?.();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Upload failed');
    } finally {
      setUploading(false);
      setProgress(0);
    }
  }, [onUploadComplete]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'], 'text/plain': ['.txt'] },
    multiple: false,
    disabled: uploading,
  });

  /* ── Delete ──────────────────────────────────── */
  const handleDelete = async (e, id, name) => {
    e.stopPropagation();
    e.preventDefault();
    if (!window.confirm(`Are you sure you want to delete "${name}"? This action cannot be undone.`)) return;
    try {
      await deleteDocument(id);
      setDocs((d) => d.filter((x) => x.id !== id));
      toast.success(`Deleted ${name}`);
    } catch {
      toast.error('Delete failed');
    }
  };

  /* ── Render ──────────────────────────────────── */
  const fmtDate = (iso) =>
    new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });

  return (
    <>
      <div className="sidebar-header">
        <h1>
          <IconSparkles className="icon-accent" size={18} />
          <span>DocMind</span>
        </h1>
        <p>Agent-native RAG System</p>
      </div>

      <div className="upload-section">
        <div
          {...getRootProps()}
          className={`dropzone ${isDragActive ? 'dropzone--active' : ''} ${
            uploading ? 'dropzone--uploading' : ''
          }`}
        >
          <input {...getInputProps()} />
          <div className="dropzone-icon">
            {uploading ? (
              <IconLoader size={32} className="icon-spin" />
            ) : (
              <IconUpload size={32} className="icon-muted" />
            )}
          </div>
          <p className="dropzone-text">
            {uploading ? (
              <span>Ingesting document...</span>
            ) : isDragActive ? (
              <span>Drop the file here...</span>
            ) : (
              <span><strong>Drop a file</strong> or click</span>
            )}
          </p>
          <p className="dropzone-hint">PDF or TXT</p>
        </div>

        {uploading && (
          <div className="upload-progress">
            <div className="progress-bar-track">
              <div
                className="progress-bar-fill"
                style={{ width: `${progress}%` }}
              />
            </div>
            <div className="progress-label">{progress}% Ingested</div>
          </div>
        )}
      </div>

      <div className="doc-library">
        <div className="doc-library-title">
          Documents {!loading && `(${docs.length})`}
        </div>

        {loading ? (
          [1, 2, 3].map((i) => (
            <div
              key={i}
              className="doc-item skeleton"
              style={{ height: '52px', marginBottom: '8px' }}
            />
          ))
        ) : docs.length === 0 ? (
          <div className="doc-empty">
            <div className="doc-empty-icon">
              <IconFolder size={32} />
            </div>
            <p>No documents uploaded yet.<br />Drop a file to get started.</p>
          </div>
        ) : (
          docs.map((doc) => (
            <div key={doc.id} className="doc-item">
              <div className="doc-item-icon">
                {doc.filename.toLowerCase().endsWith('.pdf') ? (
                  <IconFilePdf size={16} className="icon-accent" />
                ) : (
                  <IconFileText size={16} className="icon-accent" />
                )}
              </div>
              <div className="doc-item-info">
                <p className="doc-item-name" title={doc.filename}>
                  {doc.filename}
                </p>
                <p className="doc-item-date">{fmtDate(doc.created_at)}</p>
              </div>
              <button
                type="button"
                className="doc-item-delete"
                onClick={(e) => {
                  e.stopPropagation();
                  e.preventDefault();
                  if (window.confirm(`Delete ${doc.filename}?`)) {
                    deleteDocument(doc.id)
                      .then(() => {
                        fetchDocs();
                        toast.success('Document deleted');
                      })
                      .catch(() => toast.error('Failed to delete document'));
                  }
                }}
                title="Delete Document"
                style={{
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  padding: '4px',
                  color: 'inherit'
                }}
              >
                🗑
              </button>
            </div>
          ))
        )}
      </div>
    </>
  );
}
