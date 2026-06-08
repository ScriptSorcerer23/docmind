import { useState } from 'react';
import { IconChevron, IconFile } from './Icons';

export default function SourceCard({ sources }) {
  const [open, setOpen] = useState(false);
  if (!sources || !sources.length) return null;

  return (
    <div className="sources-container">
      <button className="sources-toggle" onClick={() => setOpen(!open)}>
        <IconChevron
          size={10}
          className={`sources-toggle-icon ${open ? 'sources-toggle-icon--open' : ''}`}
        />
        <span>
          {sources.length} source{sources.length > 1 ? 's' : ''} found
        </span>
      </button>

      {open && (
        <div className="sources-list">
          {sources.map((s, i) => {
            return (
              <div key={i} className="source-card">
                <div className="source-card-header">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                      <polyline points="14 2 14 8 20 8"/>
                    </svg>
                    <span className="source-card-filename" style={{ fontFamily: 'var(--font-mono)' }}>
                      {s.filename}
                    </span>
                  </div>
                  {s.page != null && (
                    <span className="source-card-meta" style={{ marginLeft: 'auto', background: 'var(--bg-tertiary)', padding: '2px 6px', borderRadius: '4px', border: '1px solid var(--border-subtle)' }}>
                      Page {(s.page || 0) + 1}
                    </span>
                  )}
                </div>

                {s.chunk_preview && (
                  <p className="source-card-preview" title={s.chunk_preview}>
                    {s.chunk_preview.slice(0, 150)}
                    {s.chunk_preview.length > 150 ? '…' : ''}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
