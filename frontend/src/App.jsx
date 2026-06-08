import { useState } from 'react';
import { Toaster } from 'react-hot-toast';
import DocumentLibrary from './components/DocumentLibrary';
import ChatInterface from './components/ChatInterface';

export default function App() {
  const [refreshKey, setRefreshKey] = useState(0);
  const triggerRefresh = () => setRefreshKey((k) => k + 1);

  return (
    <>
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: '#12121a',
            color: '#e2e8f0',
            border: '1px solid #1e1e2e',
            borderRadius: '10px',
            fontSize: '0.82rem',
            fontFamily: 'Inter, sans-serif',
          },
        }}
      />
      <div className="app-layout">
        <aside className="sidebar">
          <DocumentLibrary refreshKey={refreshKey} onUploadComplete={triggerRefresh} />
        </aside>
        <main className="main-content">
          <ChatInterface />
        </main>
      </div>
    </>
  );
}
