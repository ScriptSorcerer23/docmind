export function TypingIndicator() {
  return (
    <div className="typing-indicator">
      <span className="typing-dot" />
      <span className="typing-dot" />
      <span className="typing-dot" />
    </div>
  );
}

export function MessageSkeleton() {
  return (
    <div style={{ padding: '12px 16px' }}>
      <div className="skeleton skeleton-line" style={{ width: '90%' }} />
      <div className="skeleton skeleton-line" style={{ width: '75%' }} />
      <div className="skeleton skeleton-line" style={{ width: '60%' }} />
    </div>
  );
}
