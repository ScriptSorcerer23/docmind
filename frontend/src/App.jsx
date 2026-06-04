import { useState } from 'react';
import { Toaster } from 'react-hot-toast';
import UploadPanel from './components/UploadPanel';
import DocumentLibrary from './components/DocumentLibrary';
import ChatInterface from './components/ChatInterface';

export default function App() {
  const [refreshKey, setRefreshKey] = useState(0);

  const handleUploadComplete = () => {
    setRefreshKey((k) => k + 1);
  };

  return (
    <>
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: '#222233',
            color: '#F0F0F5',
            border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: '12px',
            fontSize: '0.85rem',
          },
        }}
      />
      <div className="app-layout">
        {/* Sidebar */}
        <aside className="sidebar">
          <div className="sidebar-header">
            <h1>🔍 DocMind</h1>
            <p>Document Intelligence Platform</p>
          </div>
          <UploadPanel onUploadComplete={handleUploadComplete} />
          <DocumentLibrary refreshKey={refreshKey} />
        </aside>

        {/* Main chat area */}
        <ChatInterface />
      </div>
    </>
  );
}
