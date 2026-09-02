'use client';

import { useState, useRef, useCallback } from 'react';

type StepEvent = {
  step_id?: string;
  status?: string;
  result?: Record<string, unknown>;
  event?: 'complete' | 'error';
  summary?: Record<string, unknown>;
  message?: string;
  gateway_elapsed_ms?: number;
};

type TimelineEntry = StepEvent & { receivedAt: number };

const GATEWAY_WS_URL = process.env.NEXT_PUBLIC_GATEWAY_WS_URL || 'ws://localhost:8080/ws';
const BACKEND_HTTP_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

export default function ChatStream() {
  const [goal, setGoal] = useState('');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [connectionState, setConnectionState] = useState<'idle' | 'connecting' | 'streaming' | 'complete' | 'error'>('idle');
  const wsRef = useRef<WebSocket | null>(null);

  const startAgentSession = useCallback(async () => {
    if (!goal.trim()) return;
    setTimeline([]);
    setConnectionState('connecting');

    // Step 1: ask the backend to plan the goal and create a session
    const res = await fetch(`${BACKEND_HTTP_URL}/session/start?goal=${encodeURIComponent(goal)}`, {
      method: 'POST',
    });
    const { session_id } = await res.json();
    setSessionId(session_id);

    // Step 2: connect to the gateway over WebSocket and ask it to stream
    // this session's execution — the gateway, not the browser, holds the
    // SSE connection to the backend, so a flaky client network doesn't
    // interrupt backend execution (session persists regardless)
    const ws = new WebSocket(GATEWAY_WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnectionState('streaming');
      ws.send(JSON.stringify({ type: 'start_session', session_id }));
    };

    ws.onmessage = (event) => {
      const data: StepEvent = JSON.parse(event.data);
      setTimeline((prev) => [...prev, { ...data, receivedAt: Date.now() }]);
      if (data.event === 'complete') setConnectionState('complete');
      if (data.event === 'error') setConnectionState('error');
    };

    ws.onerror = () => setConnectionState('error');
  }, [goal]);

  // Resume support: if the connection drops mid-plan, this calls the
  // backend's resume endpoint directly — demonstrating that "persistent
  // across sessions" isn't just a backend claim, the frontend actually
  // exercises the resume path
  const resumeSession = useCallback(async () => {
    if (!sessionId) return;
    setConnectionState('connecting');
    const res = await fetch(`${BACKEND_HTTP_URL}/session/${sessionId}/resume`, { method: 'POST' });
    const data = await res.json();
    setTimeline((prev) => [...prev, { event: 'complete', summary: data.trace_summary, receivedAt: Date.now() }]);
    setConnectionState('complete');
  }, [sessionId]);

  return (
    <div className="chat-stream">
      <div className="goal-input">
        <input
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder="e.g. research and summarize recent AI agent frameworks"
          disabled={connectionState === 'streaming'}
        />
        <button onClick={startAgentSession} disabled={connectionState === 'streaming' || connectionState === 'connecting'}>
          Run Agent
        </button>
        {connectionState === 'error' && (
          <button onClick={resumeSession}>Resume Session</button>
        )}
      </div>

      <div className="timeline">
        {timeline.map((entry, i) => (
          <div key={i} className={`timeline-entry status-${entry.status || entry.event}`}>
            {entry.step_id && <strong>{entry.step_id}</strong>}
            {entry.status && <span className="status-badge">{entry.status}</span>}
            {entry.gateway_elapsed_ms !== undefined && (
              <span className="latency">{entry.gateway_elapsed_ms}ms</span>
            )}
            {entry.event === 'complete' && (
              <div className="summary">
                Complete — {JSON.stringify(entry.summary)}
              </div>
            )}
            {entry.event === 'error' && (
              <div className="error">Connection lost: {entry.message}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
