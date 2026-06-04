import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { getDocuments, deleteDocument } from '../api/client';

export default function DocumentLibrary({ refreshKey }) {
  const [docs, setDocs] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchDocs = async () => {
    try {
      const res = await getDocuments();
      setDocs(res.data || []);
    } catch {
      /* silent */
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchDocs(); }, [refreshKey]);

  const handleDelete = async (id, name) => {
    if (!confirm(`Delete "${name}"?`)) return;
    try {
      await deleteDocument(id);
      setDocs((prev) => prev.filter((d) => d.id !== id));
      toast.success(`Deleted ${name}`);
    } catch {
      toast.error('Delete failed.');
    }
  };

  const formatDate = (iso) => {
    const d = new Date(iso);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  };

  if (loading) {
    return (
      <div className="doc-library">
        <p className="doc-library-title">Documents</p>
        {[1, 2, 3].map((i) => (
          <div key={i} className="doc-item">
            <div className="skeleton" style={{ width: 28, height: 28, borderRadius: 6 }} />
            <div style={{ flex: 1 }}>
              <div className="skeleton skeleton-line" style={{ width: '80%' }} />
              <div className="skeleton skeleton-line" style={{ width: '50%', height: 10 }} />
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="doc-library">
      <p className="doc-library-title">Documents ({docs.length})</p>
      {docs.length === 0 ? (
        <div className="doc-empty">
          <span className="doc-empty-icon">📂</span>
          <p>No documents yet.<br />Upload a file to get started.</p>
        </div>
      ) : (
        docs.map((doc) => (
          <div key={doc.id} className="doc-item">
            <span className="doc-item-icon">{doc.filename?.endsWith('.pdf') ? '📕' : '📝'}</span>
            <div className="doc-item-info">
              <p className="doc-item-name">{doc.filename}</p>
              <p className="doc-item-date">{formatDate(doc.created_at)}</p>
            </div>
            <button className="doc-item-delete" onClick={() => handleDelete(doc.id, doc.filename)} title="Delete">🗑️</button>
          </div>
        ))
      )}
    </div>
  );
}
