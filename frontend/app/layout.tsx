export const metadata = {
  title: 'Persistent AI Agent Platform',
  description: 'Full-stack multi-step agent system with streaming and session persistence',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
