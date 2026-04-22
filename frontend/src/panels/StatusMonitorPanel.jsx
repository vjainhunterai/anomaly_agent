import React, { useEffect, useMemo, useRef, useState } from 'react';
import MarkdownRenderer from '../components/MarkdownRenderer.jsx';
import api from '../services/api.js';

// Polls /status/summary + /status/contracts every 30 s. Fires
// onProcessingComplete(contracts) once per run, gated by two refs so it
// doesn't re-trigger on every tick.

const POLL_MS = 30_000;

const STATE_LABELS = {
  idle: 'Idle',
  pending: 'Queued',
  running: 'Running',
  complete: 'Complete',
  error: 'Error',
};

export default function StatusMonitorPanel({
  activeDelivery,
  onProcessingComplete,
}) {
  const [summary, setSummary] = useState(null);
  const [contracts, setContracts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [tick, setTick] = useState(0);
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState(null);
  const [askBusy, setAskBusy] = useState(false);

  const processingStartedRef = useRef(false);
  const completionFiredRef = useRef(false);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, c] = await Promise.all([
        api.statusSummary(),
        api.statusContracts(200),
      ]);
      setSummary(s);
      setContracts(c.contracts || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // manual + interval polling
  useEffect(() => {
    refresh();
    const id = setInterval(() => setTick((t) => t + 1), POLL_MS);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (tick > 0) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick]);

  // completion detection — gated refs so we fire exactly once per run
  useEffect(() => {
    if (!summary) return;
    const state = summary.processing_state;
    if (state === 'running' || state === 'pending') {
      processingStartedRef.current = true;
      completionFiredRef.current = false;
    }
    if (
      state === 'complete' &&
      processingStartedRef.current &&
      !completionFiredRef.current
    ) {
      completionFiredRef.current = true;
      onProcessingComplete?.(contracts);
    }
  }, [summary, contracts, onProcessingComplete]);

  // if the active delivery changes, reset the completion gates
  useEffect(() => {
    processingStartedRef.current = false;
    completionFiredRef.current = false;
  }, [activeDelivery?.id]);

  const askStatus = async () => {
    const q = question.trim();
    if (!q) return;
    setAskBusy(true);
    setAnswer(null);
    try {
      const res = await api.statusAsk(q);
      setAnswer(res.answer);
    } catch (err) {
      setAnswer(`⚠️ ${err.message}`);
    } finally {
      setAskBusy(false);
    }
  };

  const cards = useMemo(() => {
    if (!summary) return [];
    return [
      { label: 'Records scanned', value: summary.total_records ?? 0 },
      { label: 'Anomalies flagged', value: summary.anomalies_detected ?? 0 },
      {
        label: 'Date range',
        value:
          summary.start_date && summary.end_date
            ? `${summary.start_date} → ${summary.end_date}`
            : '—',
      },
      {
        label: 'State',
        value: STATE_LABELS[summary.processing_state] || summary.processing_state,
        tone: summary.processing_state,
      },
    ];
  }, [summary]);

  return (
    <div className="panel-inner">
      <header className="panel-header">
        <h2>Status Monitor</h2>
        <div className="panel-header-right">
          <span className="muted">
            {summary?.last_updated
              ? `updated ${new Date(summary.last_updated).toLocaleTimeString()}`
              : 'never updated'}
          </span>
          <button
            className="btn btn-sm btn-ghost"
            onClick={refresh}
            disabled={loading}
          >
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </header>

      {error && <div className="panel-error">{error}</div>}

      <div className="status-cards">
        {cards.map((c) => (
          <div key={c.label} className={`status-card tone-${c.tone || 'neutral'}`}>
            <div className="status-card-label">{c.label}</div>
            <div className="status-card-value">{c.value}</div>
          </div>
        ))}
      </div>

      <div className="contracts-block">
        <div className="contracts-block-header">
          <h3>Records</h3>
          <span className="muted">
            {contracts.length} shown{' '}
            {activeDelivery ? `· ${activeDelivery.label}` : ''}
          </span>
        </div>
        <div className="contracts-table-wrap">
          <ContractsTable rows={contracts} />
        </div>
      </div>

      <div className="status-ask">
        <div className="chat-input-row">
          <input
            type="text"
            placeholder="Ask about current status (e.g. how many high-severity?)"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && askStatus()}
          />
          <button
            className="btn btn-primary"
            onClick={askStatus}
            disabled={askBusy || !question.trim()}
          >
            {askBusy ? 'Asking…' : 'Ask'}
          </button>
        </div>
        {answer && (
          <div className="status-answer">
            <MarkdownRenderer text={answer} />
          </div>
        )}
      </div>
    </div>
  );
}

function ContractsTable({ rows }) {
  if (!rows?.length) {
    return <div className="empty">No records yet. Trigger a run to see data here.</div>;
  }
  const allKeys = Array.from(
    rows
      .slice(0, 25)
      .reduce(
        (acc, r) => {
          Object.keys(r.fields || {}).forEach((k) => acc.add(k));
          return acc;
        },
        new Set(['id', 'status'])
      )
  );
  // keep first 8 columns for width
  const keys = allKeys.slice(0, 8);
  return (
    <table className="grid-table">
      <thead>
        <tr>
          {keys.map((k) => (
            <th key={k}>{k}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.slice(0, 50).map((r, idx) => (
          <tr key={idx} className={`row-${r.status}`}>
            {keys.map((k) => {
              const v =
                k === 'id' || k === 'status' ? r[k] : r.fields?.[k];
              return <td key={k}>{v == null ? '' : String(v)}</td>;
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
