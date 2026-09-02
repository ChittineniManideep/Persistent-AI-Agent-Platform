import ChatStream from '../components/ChatStream';

export default function Home() {
  return (
    <main style={{ maxWidth: 720, margin: '0 auto', padding: '2rem' }}>
      <h1>Persistent AI Agent Platform</h1>
      <p style={{ color: '#666', marginBottom: '1.5rem' }}>
        Enter a goal. The agent plans it into steps, streams progress in
        real time, and can resume from exactly where it left off if the
        connection drops mid-execution.
      </p>
      <ChatStream />
    </main>
  );
}
