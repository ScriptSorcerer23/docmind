import { useState, useRef, useEffect } from 'react';
import { sendMessage } from '../api/client';
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
  const [agentStep, setAgentStep] = useState(0);
  const [currentSteps, setCurrentSteps] = useState(['Analyzing query…']);
  const containerRef = useRef(null);
  const inputRef = useRef(null);

  const scrollToBottom = () => {
    const el = containerRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading, agentStep]);

  /* ── Send ────────────────────────────────────── */
  const buildHistory = () => messages.map((m) => ({ role: m.role, content: m.content }));

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading) return;

    setMessages((prev) => [...prev, { role: 'user', content: text }]);
    setInput('');
    setLoading(true);
    setCurrentSteps(['Analyzing query…']);
    setAgentStep(0);

    try {
      const res = await sendMessage(text, buildHistory());
      const { answer, sources } = res.data;

      if (sources && sources.length > 0) {
        // Show "Searching documents..." for 800ms
        setCurrentSteps([
          'Analyzing query…',
          'Searching documents…',
          'Synthesizing answer…',
        ]);
        setAgentStep(1);
        await new Promise((resolve) => setTimeout(resolve, 800));

        // Show "Synthesizing answer..." for 800ms
        setAgentStep(2);
        await new Promise((resolve) => setTimeout(resolve, 800));
      } else {
        // Skip "Searching documents..." and go straight to "Synthesizing answer..." for 800ms
        setCurrentSteps([
          'Analyzing query…',
          'Synthesizing answer…',
        ]);
        setAgentStep(1);
        await new Promise((resolve) => setTimeout(resolve, 800));
      }

      setMessages((prev) => [...prev, { role: 'assistant', content: answer, sources }]);
    } catch (err) {
      const errorMessage = err.response?.data?.detail || 'Something went wrong. Please try again.';
      toast.error(errorMessage);
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: errorMessage,
          sources: [],
        },
      ]);
    } finally {
      setLoading(false);
      // Use setTimeout to allow browser input to re-enable before focusing
      setTimeout(() => {
        inputRef.current?.focus();
      }, 50);
    }
  };

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

          {/* Agent thinking indicator */}
          {loading && (
            <div className="message message--assistant">
              <div className="message-avatar message-avatar--active">
                <IconBot size={14} />
              </div>
              <div className="agent-steps">
                {currentSteps.map((step, i) => (
                  <div
                    key={i}
                    className={`agent-step ${i <= agentStep ? 'agent-step--active' : ''} ${
                      i === agentStep ? 'agent-step--current' : ''
                    }`}
                  >
                    <span className="agent-step__dot" />
                    <span>{step}</span>
                  </div>
                ))}
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
