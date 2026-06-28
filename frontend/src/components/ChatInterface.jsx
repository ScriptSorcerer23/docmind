import { useState, useRef, useEffect, useCallback } from 'react';
import { streamMessage } from '../api/client';
import SourceCard from './SourceCard';
import { IconUser, IconBot, IconSend, IconLoader, IconSparkles } from './Icons';
import toast from 'react-hot-toast';

const parseMessageContent = (content) => {
  if (!content) return null;

  const parts = content.split(/(```[\s\S]*?```)/g);

  const testRegex = new RegExp(
    '^' +
    '(?:' +
    '[\\w\\.\\-\\+\\/\\\\]*[/\\\\][\\w\\-\\+\\/\\\\]+\\.[a-zA-Z0-9]{2,5}' +
    '|' +
    'v\\d+\\.\\d+\\.\\d+(?:-\\w+)?' +
    '|' +
    '[a-zA-Z0-9]{17,}' +
    '|' +
    '(?:gpt|claude|llama|gemini|mixtral|deepseek)-\\w+(?:-\\w+)*' +
    ')' +
    '$'
  );

  const techRegex = new RegExp(
    '(' +
    '[\\w\\.\\-\\+\\/\\\\]*[/\\\\][\\w\\-\\+\\/\\\\]+\\.[a-zA-Z0-9]{2,5}' +
    '|' +
    '\\bv\\d+\\.\\d+\\.\\d+(?:-\\w+)?\\b' +
    '|' +
    '\\b[a-zA-Z0-9]{17,}\\b' +
    '|' +
    '\\b(?:gpt|claude|llama|gemini|mixtral|deepseek)-\\w+(?:-\\w+)*\\b' +
    ')',
    'g'
  );

  return parts.map((part, index) => {
    if (part.startsWith('```') && part.endsWith('```')) {
      const codeLines = part.slice(3, -3).trim().split('\n');
      const firstLine = codeLines[0];
      const hasLang = /^[a-zA-Z0-9_-]+$/.test(firstLine);
      const codeText = (hasLang ? codeLines.slice(1) : codeLines).join('\n');

      return (
        <pre key={index} className="system-output-block">
          <code>{codeText}</code>
        </pre>
      );
    }

    const lines = part.split('\n');
    return (
      <div key={index} className="message-paragraph">
        {lines.map((line, lineIdx) => {
          const trimmedLine = line.trim();

          if (trimmedLine.startsWith('>')) {
            const systemText = line.substring(line.indexOf('>') + 1);
            return (
              <div key={lineIdx} className="system-output-line">
                {systemText}
              </div>
            );
          }

          const inlineParts = line.split(/(`[^`\n]+`)/g);

          const parsedLineContent = inlineParts.map((subPart, subIdx) => {
            if (subPart.startsWith('`') && subPart.endsWith('`')) {
              const inlineCode = subPart.slice(1, -1);
              return (
                <code key={subIdx} className="inline-code-span">
                  {inlineCode}
                </code>
              );
            }

            const techParts = subPart.split(techRegex);
            return techParts.map((techPart, techIdx) => {
              if (testRegex.test(techPart)) {
                return (
                  <span key={techIdx} className="tech-token">
                    {techPart}
                  </span>
                );
              }
              return techPart;
            });
          });

          return (
            <div key={lineIdx} className="message-line">
              {parsedLineContent}
            </div>
          );
        })}
      </div>
    );
  });
};

export default function ChatInterface() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  // liveSteps: real tool events from the SSE stream, in arrival order.
  // Each entry: { id, tool, callText, resultText, status: 'pending'|'done' }
  const [liveSteps, setLiveSteps] = useState([]);
  const containerRef = useRef(null);
  const inputRef = useRef(null);
  const abortRef = useRef(null);

  const scrollToBottom = () => {
    const el = containerRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading, liveSteps]);

  /* ── Human-readable labels for each tool ──────────────────── */
  const toolLabel = (toolName, args = {}) => {
    switch (toolName) {
      case 'retrieve_documents':
        return args.query
          ? `Searching for “${args.query}”…`
          : 'Searching uploaded documents…';
      case 'list_available_documents':
        return 'Listing available documents…';
      case 'summarize_document':
        return args.filename
          ? `Summarizing ${args.filename}…`
          : 'Summarizing document…';
      case 'compare_documents':
        return args.filenames
          ? `Comparing ${args.filenames}…`
          : 'Comparing documents…';
      default:
        return `Calling ${toolName}…`;
    }
  };

  /* ── Send ─────────────────────────────────────── */
  const buildHistory = () => messages.map((m) => ({ role: m.role, content: m.content }));

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;

    // Cancel any ongoing request.
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setMessages((prev) => [...prev, { role: 'user', content: text }]);
    setInput('');
    setLoading(true);
    setLiveSteps([]);  // clear previous run's steps

    // stepMap: tool_call_id → index in liveSteps array
    // Since the API doesn’t expose tool_call_id in SSE, we key on tool name + arrival order.
    // A simple counter is sufficient: tool_call always precedes tool_result for the same tool.
    let stepCounter = 0;

    try {
      await streamMessage(text, buildHistory(), {
        signal: controller.signal,
        onEvent: (event) => {
          if (event.type === 'tool_call') {
            const stepId = stepCounter++;
            setLiveSteps((prev) => [
              ...prev,
              {
                id: stepId,
                tool: event.tool,
                callText: toolLabel(event.tool, event.args || {}),
                resultText: null,
                status: 'pending',
              },
            ]);
          } else if (event.type === 'tool_result') {
            // Update the most-recently-added step that matches this tool and is still pending.
            setLiveSteps((prev) => {
              const idx = [...prev].reverse().findIndex(
                (s) => s.tool === event.tool && s.status === 'pending'
              );
              if (idx === -1) return prev;
              const realIdx = prev.length - 1 - idx;
              const updated = [...prev];
              updated[realIdx] = {
                ...updated[realIdx],
                resultText: event.summary,
                status: 'done',
              };
              return updated;
            });
          } else if (event.type === 'done') {
            setMessages((prev) => [
              ...prev,
              { role: 'assistant', content: event.answer, sources: event.sources || [] },
            ]);
            setLiveSteps([]);
            setLoading(false);
            setTimeout(() => inputRef.current?.focus(), 50);
          } else if (event.type === 'error') {
            toast.error(event.message);
            setMessages((prev) => [
              ...prev,
              { role: 'assistant', content: event.message, sources: [] },
            ]);
            setLiveSteps([]);
            setLoading(false);
            setTimeout(() => inputRef.current?.focus(), 50);
          }
        },
      });
    } catch (err) {
      if (err.name === 'AbortError') return;  // user cancelled
      const msg = err.message || 'Something went wrong. Please try again.';
      toast.error(msg);
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: msg, sources: [] },
      ]);
      setLiveSteps([]);
      setLoading(false);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [input, loading, messages]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const hasMessages = messages.length > 0;

  return (
    <>
      {/* Header */}
      <div className="chat-header">
        <span className="chat-header-title">Agent Console</span>
        <div className="chat-header-badge">
          <span className="chat-header-dot" />
          <span>Active Agent</span>
        </div>
      </div>

      {/* Messages / Empty State */}
      {!hasMessages && !loading ? (
        <div className="welcome-state">
          <div className="welcome-icon-wrapper">
            <IconSparkles size={36} className="icon-accent" />
          </div>
          <h2 className="welcome-title">DocMind AI Agent</h2>
          <p className="welcome-subtitle">
            Upload a document, then ask anything about it.
          </p>
        </div>
      ) : (
        <div className="chat-messages" ref={containerRef}>
          {messages.map((msg, i) => (
            <div key={i} className={`message message--${msg.role}`}>
              <div className="message-avatar">
                {msg.role === 'user' ? (
                  <IconUser size={14} />
                ) : (
                  <IconBot size={14} />
                )}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', flex: 1, minWidth: 0 }}>
                <div className="message-bubble">
                  {msg.role === 'assistant' ? parseMessageContent(msg.content) : msg.content}
                </div>
                {msg.role === 'assistant' && <SourceCard sources={msg.sources} />}
              </div>
            </div>
          ))}

          {/* Agent thinking indicator — real SSE steps */}
          {loading && (
            <div className="message message--assistant">
              <div className="message-avatar message-avatar--active">
                <IconBot size={14} />
              </div>
              <div className="agent-steps">
                {liveSteps.length === 0 ? (
                  /* No tool calls yet — show a generic thinking dot */
                  <div className="agent-step agent-step--current">
                    <span className="agent-step__dot" />
                    <span>Thinking…</span>
                  </div>
                ) : (
                  liveSteps.map((step) => (
                    <div key={step.id}>
                      {/* tool_call row */}
                      <div
                        className={`agent-step ${
                          step.status === 'pending' ? 'agent-step--current' : 'agent-step--active'
                        }`}
                      >
                        <span className="agent-step__dot" />
                        <span>🔧 {step.callText}</span>
                      </div>
                      {/* tool_result row — only when complete */}
                      {step.resultText && (
                        <div className="agent-step agent-step--active" style={{ paddingLeft: '18px' }}>
                          <span className="agent-step__dot" style={{ background: 'var(--success)', boxShadow: 'none' }} />
                          <span style={{ color: 'var(--success)' }}>✓ {step.resultText}</span>
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Input Area */}
      <div className="chat-input-area">
        <div className={`chat-input-wrapper ${loading ? 'processing' : ''}`}>
          <textarea
            ref={inputRef}
            className="chat-input"
            placeholder={loading ? 'Agent is working…' : 'Ask about your documents…'}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={1}
          />
          <button
            className="chat-send-btn"
            onClick={handleSend}
            disabled={!input.trim() || loading}
          >
            {loading ? (
              <IconLoader size={16} className="icon-spin" />
            ) : (
              <IconSend size={15} />
            )}
          </button>
        </div>
      </div>
    </>
  );
}
