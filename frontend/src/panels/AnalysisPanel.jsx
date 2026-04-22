import React, { useEffect, useRef, useState } from 'react';
import MarkdownRenderer from '../components/MarkdownRenderer.jsx';
import api from '../services/api.js';

// Analyst panel:
//   1. Let the user pick a delivery (or auto-pick on processingComplete).
//   2. Call /analysis/setup to run understanding + anomaly detection.
//   3. Auto-fire /reports/reconciliation.
//   4. Free-form follow-up Q&A that may also return a SQL query.

export default function AnalysisPanel({
  sessionId,
  activeDelivery,
  processingComplete,
}) {
  const [deliveries, setDeliveries] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [setup, setSetup] = useState(null); // AnalysisSetupResponse
  const [setupError, setSetupError] = useState(null);
  const [setupBusy, setSetupBusy] = useState(false);

  const [reconciliation, setReconciliation] = useState(null);
  const [reconBusy, setReconBusy] = useState(false);

  const [question, setQuestion] = useState('');
  const [qa, setQa] = useState([]); // { q, a, sql, rows }
  const [askBusy, setAskBusy] = useState(false);
  const [askError, setAskError] = useState(null);

  const autoFiredRef = useRef(false);

  useEffect(() => {
    let alive = true;
    api
      .deliveries()
      .then((r) => {
        if (!alive) return;
        setDeliveries(r.deliveries || []);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [processingComplete, activeDelivery?.id]);

  // preselect the currently active delivery
  useEffect(() => {
    if (activeDelivery?.id && !selectedId) setSelectedId(activeDelivery.id);
  }, [activeDelivery, selectedId]);

  const runSetup = async (delivery) => {
    if (!delivery) return;
    setSetupBusy(true);
    setSetupError(null);
    setSetup(null);
    setReconciliation(null);
    try {
      const payload = {
        session_id: sessionId || null,
        delivery_id: delivery.id,
        start_date: delivery.start_date || null,
        end_date: delivery.end_date || null,
      };
      const res = await api.setupAnalysis(payload);
      setSetup(res);
      // immediately fire reconciliation
      fireReconciliation(res.session_id);
    } catch (err) {
      setSetupError(err.message);
    } finally {
      setSetupBusy(false);
    }
  };

  const fireReconciliation = async (sid) => {
    setReconBusy(true);
    try {
      const res = await api.reconciliation(sid);
      setReconciliation(res);
    } catch (err) {
      setReconciliation({ report: `⚠️ ${err.message}`, summary: null });
    } finally {
      setReconBusy(false);
    }
  };

  // auto-fire when processing completes
  useEffect(() => {
    if (!processingComplete || autoFiredRef.current) return;
    const target =
      deliveries.find((d) => d.id === (activeDelivery?.id || selectedId)) ||
      activeDelivery ||
      deliveries[0];
    if (!target) return;
    autoFiredRef.current = true;
    setSelectedId(target.id);
    runSetup(target);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [processingComplete, deliveries]);

  const manualSetup = () => {
    const target =
      deliveries.find((d) => d.id === selectedId) ||
      (activeDelivery?.id === selectedId ? activeDelivery : null);
    if (!target) {
      setSetupError('Select a delivery first.');
      return;
    }
    runSetup(target);
  };

  const askQuestion = async () => {
    const q = question.trim();
    if (!q || !setup?.session_id) return;
    setAskBusy(true);
    setAskError(null);
    try {
      const res = await api.askAnalysis(setup.session_id, q);
      setQa((prev) => [
        ...prev,
        { q, a: res.answer, sql: res.sql, rows: res.rows },
      ]);
      setQuestion('');
    } catch (err) {
      setAskError(err.message);
    } finally {
      setAskBusy(false);
    }
  };

  const showPickerOnly = !setup && !setupBusy;

  return (
    <div className="panel-inner">
      <header className="panel-header">
        <h2>Analysis</h2>
        {setup?.delivery?.label && (
          <span className="muted">{setup.delivery.label}</span>
        )}
      </header>

      <div className="analysis-setup">
        <label className="field">
          <span>Delivery</span>
          <select
            value={selectedId}
            onChange={(e) => setSelectedId(e.target.value)}
            disabled={setupBusy}
          >
            <option value="">— select a run —</option>
            {deliveries.map((d) => (
              <option key={d.id} value={d.id}>
                {d.label}
              </option>
            ))}
          </select>
        </label>
        <button
          className="btn btn-primary"
          onClick={manualSetup}
          disabled={setupBusy || !selectedId}
        >
          {setupBusy ? 'Analyzing…' : 'Run analysis'}
        </button>
      </div>

      {setupError && <div className="panel-error">{setupError}</div>}

      {showPickerOnly && (
        <div className="empty">
          Trigger a pipeline run from the chat panel, or pick an existing
          delivery above and click <strong>Run analysis</strong>.
        </div>
      )}

      {setup && (
        <div className="analysis-output">
          <section className="analysis-section">
            <h3>Dataset Understanding</h3>
            <MarkdownRenderer text={setup.understanding} />
          </section>

          <section className="analysis-section">
            <h3>Reconciliation Report</h3>
            {reconBusy && <div className="muted">Generating…</div>}
            {reconciliation && (
              <MarkdownRenderer text={reconciliation.report} />
            )}
          </section>

          <section className="analysis-section">
            <h3>
              Anomalies detected{' '}
              <span className="pill">{setup.anomalies?.length || 0}</span>
            </h3>
            <MarkdownRenderer text={setup.final_output} />
          </section>

          <section className="analysis-section">
            <h3>Ask a follow-up</h3>
            <div className="chat-input-row">
              <input
                type="text"
                placeholder="e.g. Which vendor has the most duplicates?"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && askQuestion()}
                disabled={askBusy}
              />
              <button
                className="btn btn-primary"
                onClick={askQuestion}
                disabled={askBusy || !question.trim()}
              >
                {askBusy ? 'Asking…' : 'Ask'}
              </button>
            </div>
            {askError && <div className="panel-error">{askError}</div>}

            <div className="qa-list">
              {qa.map((entry, idx) => (
                <div key={idx} className="qa-entry">
                  <div className="qa-q">
                    <strong>Q:</strong> {entry.q}
                  </div>
                  <div className="qa-a">
                    <MarkdownRenderer text={entry.a} />
                  </div>
                  {entry.sql && (
                    <details className="qa-sql">
                      <summary>Generated SQL</summary>
                      <pre>
                        <code>{entry.sql}</code>
                      </pre>
                      {entry.rows && entry.rows.length > 0 && (
                        <div className="qa-rows">
                          <MiniTable rows={entry.rows} />
                        </div>
                      )}
                    </details>
                  )}
                </div>
              ))}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

function MiniTable({ rows }) {
  if (!rows?.length) return <div className="muted">No rows.</div>;
  const keys = Object.keys(rows[0]);
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
        {rows.slice(0, 25).map((r, idx) => (
          <tr key={idx}>
            {keys.map((k) => (
              <td key={k}>{r[k] == null ? '' : String(r[k])}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
