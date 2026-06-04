import { useState, useRef, useEffect } from 'react';
import { sendMessage } from '../api/client';
import SourceCard from './SourceCard';
import { TypingIndicator } from './LoadingStates';

export default function ChatInterface() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => { scrollToBottom(); }, [messages, loading]);

  const buildHistory = () =>
    messages.map((m) => ({ role: m.role, content: m.content }));

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg = { role: 'user', content: text };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const res = await sendMessage(text, buildHistory());
      const { answer, sources } = res.data;
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: answer, sources },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: 'Sorry, something went wrong. Please try again.', sources: [] },
      ]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleChipClick = (text) => {
    setInput(text);
    inputRef.current?.focus();
  };

  const hasMessages = messages.length > 0;

  return (
    <div className="main-content">
      {/* Header */}
      <div className="chat-header">
        <span className="chat-header-title">Chat</span>
        <span className="chat-header-badge">
          <span className="chat-header-dot" />
          MCP Agent Online
        </span>
      </div>

      {/* Messages or Welcome */}
      {!hasMessages ? (
        <div className="welcome-state">
          <span className="welcome-icon">🧠</span>
          <h2 className="welcome-title">Document Intelligence</h2>
          <p className="welcome-subtitle">
            Upload a document and ask questions. The AI agent decides when to search your documents — and when to answer directly.
          </p>
          <div className="welcome-chips">
            <button className="welcome-chip" onClick={() => handleChipClick('What does the document say about...')}>
              📖 Ask about a document
            </button>
            <button className="welcome-chip" onClick={() => handleChipClick('Summarize the key findings')}>
              📋 Summarize findings
            </button>
            <button className="welcome-chip" onClick={() => handleChipClick('Hello!')}>
              👋 Say hello
            </button>
          </div>
        </div>
      ) : (
        <div className="chat-messages" id="chat-messages">
          {messages.map((msg, i) => (
            <div key={i} className={`message message--${msg.role}`}>
              <div className="message-avatar">
                {msg.role === 'user' ? '👤' : '🤖'}
              </div>
              <div>
                <div className="message-bubble">{msg.content}</div>
                {msg.role === 'assistant' && <SourceCard sources={msg.sources} />}
              </div>
            </div>
          ))}
          {loading && (
            <div className="message message--assistant">
              <div className="message-avatar">🤖</div>
              <div className="message-bubble">
                <TypingIndicator />
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      )}

      {/* Input */}
      <div className="chat-input-area">
        <div className="chat-input-wrapper">
          <textarea
            ref={inputRef}
            className="chat-input"
            placeholder="Ask about your documents..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={1}
            disabled={loading}
            id="chat-input"
          />
          <button
            className="chat-send-btn"
            onClick={handleSend}
            disabled={!input.trim() || loading}
            id="send-button"
          >
            ➤
          </button>
        </div>
      </div>
    </div>
  );
}
