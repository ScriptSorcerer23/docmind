import { useState } from 'react';

export default function SourceCard({ sources }) {
  const [open, setOpen] = useState(false);

  if (!sources || sources.length === 0) return null;

  return (
    <div className="sources-container">
      <button className="sources-toggle" onClick={() => setOpen(!open)}>
        <span className={`sources-toggle-icon ${open ? 'sources-toggle-icon--open' : ''}`}>▶</span>
        {sources.length} source{sources.length > 1 ? 's' : ''} cited
      </button>
      {open && (
        <div className="sources-list">
          {sources.map((s, i) => (
            <div key={i} className="source-card">
              <div className="source-card-header">
                <span className="source-card-filename">📄 {s.filename}</span>
                <span className="source-card-meta">
                  {s.page != null && `Page ${s.page}`}
                  {s.similarity != null && ` · ${(s.similarity * 100).toFixed(0)}% match`}
                </span>
              </div>
              {s.chunk_preview && <p className="source-card-preview">{s.chunk_preview}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
