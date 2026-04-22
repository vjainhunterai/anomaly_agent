import React, { useEffect, useRef, useState } from 'react';
import MarkdownRenderer from '../components/MarkdownRenderer.jsx';
import api from '../services/api.js';

// Step-based chat UI. The backend holds the FSM; this panel just pushes
// messages and renders whatever the backend returns, extracting the
// start/end date pair when the agent confirms it.

const STEP_LABELS = {
  greet: 'Greeting',
  await_dates: 'Awaiting date range',
  confirm: 'Confirm range',
  processing: 'Pipeline triggered',
  done: 'Done',
  error: 'Error',
};

export default function AgentChatPanel({ onSessionStarted, onRangeSelected }) {
  const [sessionId, setSessionId] = useState(null);
  const [step, setStep] = useState('greet');
  const [messages, setMessages] = useState([]); // { role, content }
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const logRef = useRef(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const res = await api.startAgent();
        if (!alive) return;
        setSessionId(res.session_id);
        setStep(res.step);
        setMessages([{ role: 'assistant', content: res.message }]);
        onSessionStarted?.(res.session_id, res.message);
      } catch (err) {
        if (alive) setError(err.message);
      }
    })();
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [messages]);

  const send = async () => {
    const text = input.trim();
    if (!text || !sessionId || busy) return;
    setError(null);
    setBusy(true);
    setMessages((m) => [...m, { role: 'user', content: text }]);
    setInput('');
    try {
      const res = await api.chat(sessionId, text);
      setStep(res.step);
      setMessages((m) => [...m, { role: 'assistant', content: res.message }]);
      if (res.start_date && res.end_date) {
        onRangeSelected?.({
          start_date: res.start_date,
          end_date: res.end_date,
        });
      }
    } catch (err) {
      setError(err.message);
      setMessages((m) => [
        ...m,
        { role: 'assistant', content: `⚠️ ${err.message}` },
      ]);
    } finally {
      setBusy(false);
    }
  };

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  const quickReply = (label) => {
    setInput(label);
    setTimeout(send, 0);
  };

  return (
    <div className="panel-inner">
      <header className="panel-header">
        <h2>Agent Chat</h2>
        <span className={`step-chip step-${step}`}>
          {STEP_LABELS[step] || step}
        </span>
      </header>

      <div className="chat-log" ref={logRef}>
        {messages.map((m, idx) => (
          <div key={idx} className={`chat-msg chat-msg-${m.role}`}>
            <div className="chat-msg-role">
              {m.role === 'user' ? 'You' : 'Agent'}
            </div>
            {m.role === 'assistant' ? (
              <MarkdownRenderer text={m.content} />
            ) : (
              <div className="chat-msg-body">{m.content}</div>
            )}
          </div>
        ))}
        {busy && (
          <div className="chat-msg chat-msg-assistant">
            <div className="chat-msg-role">Agent</div>
            <div className="typing">
              <span />
              <span />
              <span />
            </div>
          </div>
        )}
      </div>

      {step === 'confirm' && (
        <div className="quick-replies">
          <button className="btn btn-sm" onClick={() => quickReply('confirm')}>
            Confirm & run
          </button>
          <button className="btn btn-sm btn-ghost" onClick={() => quickReply('cancel')}>
            Cancel
          </button>
        </div>
      )}

      {error && <div className="panel-error">{error}</div>}

      <div className="chat-input-row">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder={
            step === 'await_dates'
              ? 'e.g. 2024-01-01 to 2024-12-31'
              : step === 'confirm'
              ? 'Type confirm, or enter a new range'
              : 'Message the agent…'
          }
          rows={2}
          disabled={busy || step === 'done'}
        />
        <button
          className="btn btn-primary"
          onClick={send}
          disabled={busy || !input.trim() || step === 'done'}
        >
          Send
        </button>
      </div>
    </div>
  );
}
