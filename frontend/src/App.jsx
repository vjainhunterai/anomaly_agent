import React, { useCallback, useEffect, useState } from 'react';
import AgentChatPanel from './panels/AgentChatPanel.jsx';
import StatusMonitorPanel from './panels/StatusMonitorPanel.jsx';
import AnalysisPanel from './panels/AnalysisPanel.jsx';
import api from './services/api.js';

export default function App() {
  const [sessionId, setSessionId] = useState(null);
  const [activeDelivery, setActiveDelivery] = useState(null); // { id, label, start_date, end_date }
  const [activeContracts, setActiveContracts] = useState([]); // rows from /status/contracts
  const [processingComplete, setProcessingComplete] = useState(false);
  const [health, setHealth] = useState(null);
  const [resetKey, setResetKey] = useState(0);

  // on first mount: ping health, start a session
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const h = await api.health();
        if (alive) setHealth(h);
      } catch (err) {
        if (alive) setHealth({ status: 'down', error: err.message });
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  const handleSessionStarted = useCallback((id, firstAgentMessage) => {
    setSessionId(id);
    setActiveDelivery(null);
    setProcessingComplete(false);
    // firstAgentMessage is handled inside AgentChatPanel
    void firstAgentMessage;
  }, []);

  const handleAgentRangeSelected = useCallback((range) => {
    if (!range?.start_date || !range?.end_date) return;
    setActiveDelivery({
      id: `run_${range.start_date}_${range.end_date}`,
      label: `${range.start_date} → ${range.end_date}`,
      start_date: range.start_date,
      end_date: range.end_date,
    });
  }, []);

  const handleProcessingComplete = useCallback((contracts) => {
    setProcessingComplete(true);
    if (contracts) setActiveContracts(contracts);
  }, []);

  const handleNewSession = useCallback(() => {
    setSessionId(null);
    setActiveDelivery(null);
    setActiveContracts([]);
    setProcessingComplete(false);
    setResetKey((k) => k + 1);
  }, []);

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <span className="brand-dot" />
          <h1>Anomaly Agent</h1>
          <span className="brand-sub">Duplicate AP Invoice Detection</span>
        </div>
        <div className="header-actions">
          <HealthBadge health={health} />
          <button className="btn btn-ghost" onClick={handleNewSession}>
            New Session
          </button>
        </div>
      </header>

      <main className="three-panel">
        <section className="panel panel-chat">
          <AgentChatPanel
            key={`chat-${resetKey}`}
            onSessionStarted={handleSessionStarted}
            onRangeSelected={handleAgentRangeSelected}
            sessionId={sessionId}
          />
        </section>

        <section className="panel panel-status">
          <StatusMonitorPanel
            key={`status-${resetKey}`}
            activeDelivery={activeDelivery}
            onProcessingComplete={handleProcessingComplete}
          />
        </section>

        <section className="panel panel-analysis">
          <AnalysisPanel
            key={`analysis-${resetKey}`}
            sessionId={sessionId}
            activeDelivery={activeDelivery}
            activeContracts={activeContracts}
            processingComplete={processingComplete}
          />
        </section>
      </main>

      <footer className="app-footer">
        <span>FastAPI :: {import.meta.env.MODE} mode</span>
        <span>v1.0.0</span>
      </footer>
    </div>
  );
}

function HealthBadge({ health }) {
  if (!health) return <span className="badge badge-muted">checking…</span>;
  const ok = health.status === 'ok' && health.db === 'ok';
  return (
    <span className={`badge ${ok ? 'badge-ok' : 'badge-warn'}`}>
      {ok ? 'backend ok' : `backend: ${health.status}/${health.db || 'n/a'}`}
    </span>
  );
}
