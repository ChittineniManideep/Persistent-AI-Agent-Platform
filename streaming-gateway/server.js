/**
 * Streaming gateway — sits between the Next.js frontend and the FastAPI
 * agent backend. Owns WebSocket connection lifecycle, reconnection, and
 * backpressure — the part of "real-time streaming with latency
 * constraints" that lives outside the agent logic itself.
 */
const WebSocket = require('ws');
const http = require('http');
const { EventSource } = require('eventsource');

const PORT = process.env.PORT || 8080;
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

const server = http.createServer((req, res) => {
  if (req.url === '/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok' }));
    return;
  }
  res.writeHead(404);
  res.end();
});

const wss = new WebSocket.Server({ server, path: '/ws' });

// Per-connection latency tracking — every message forwarded from the
// backend's SSE stream to the client is timestamped, so a slow step is
// visible to the client immediately rather than surfacing only as an
// overall timeout
function forwardBackendStream(ws, sessionId) {
  const es = new EventSource(`${BACKEND_URL}/session/${sessionId}/stream`);
  const startTime = Date.now();

  es.onmessage = (event) => {
    if (ws.readyState !== WebSocket.OPEN) {
      es.close();
      return;
    }
    const data = JSON.parse(event.data);
    const elapsedMs = Date.now() - startTime;

    // Backpressure guard: if the client's send buffer is backing up
    // (slow network, client not reading fast enough), skip forwarding
    // intermediate step events rather than let memory grow unbounded —
    // the final 'complete' event is never dropped
    if (ws.bufferedAmount > 1_000_000 && data.event !== 'complete') {
      console.warn(`[backpressure] dropping intermediate event for session ${sessionId}, buffered=${ws.bufferedAmount}`);
      return;
    }

    ws.send(JSON.stringify({ ...data, gateway_elapsed_ms: elapsedMs }));

    if (data.event === 'complete') {
      es.close();
    }
  };

  es.onerror = (err) => {
    console.error(`[stream error] session ${sessionId}:`, err.message);
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ event: 'error', message: 'Backend stream disconnected' }));
    }
    es.close();
  };

  return es;
}

wss.on('connection', (ws) => {
  let activeStream = null;
  console.log('[gateway] client connected');

  ws.on('message', (raw) => {
    const msg = JSON.parse(raw.toString());

    if (msg.type === 'start_session' && msg.session_id) {
      if (activeStream) activeStream.close();
      activeStream = forwardBackendStream(ws, msg.session_id);
    }

    if (msg.type === 'ping') {
      ws.send(JSON.stringify({ type: 'pong', server_time: Date.now() }));
    }
  });

  ws.on('close', () => {
    console.log('[gateway] client disconnected');
    if (activeStream) activeStream.close();
    // Deliberately do NOT tear down the backend session here — this is
    // what makes the agent session persistent across a dropped
    // connection: the backend keeps executing/holding state, and a
    // reconnecting client can resume via /session/{id}/resume
  });

  ws.on('error', (err) => console.error('[gateway] ws error:', err.message));
});

server.listen(PORT, () => {
  console.log(`Streaming gateway listening on port ${PORT}, proxying to ${BACKEND_URL}`);
});

module.exports = { server, wss };
