import { useCallback, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import toast from 'react-hot-toast';
import { uploadDocument } from '../api/client';
import { IconUpload, IconDownload, IconLoader } from './Icons';

export default function UploadPanel({ onUploadComplete }) {
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);

  const onDrop = useCallback(async (acceptedFiles) => {
    if (acceptedFiles.length === 0) return;
    const file = acceptedFiles[0];
    const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
    if (!['.pdf', '.txt'].includes(ext)) {
      toast.error('Only PDF and TXT files are supported.');
      return;
    }

    setUploading(true);
    setProgress(0);
    try {
      const res = await uploadDocument(file, (p) => setProgress(p));
      toast.success(`${res.data.filename} — ${res.data.chunk_count} chunks indexed`, { duration: 4000 });
      onUploadComplete?.(res.data);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Upload failed.');
    } finally {
      setUploading(false);
      setProgress(0);
    }
  }, [onUploadComplete]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'], 'text/plain': ['.txt'] },
    multiple: false,
    disabled: uploading,
  });

  return (
    <div className="upload-section">
      <div {...getRootProps()} className={`dropzone ${isDragActive ? 'dropzone--active' : ''} ${uploading ? 'dropzone--uploading' : ''}`} id="upload-dropzone">
        <input {...getInputProps()} id="file-input" />
        <span className="dropzone-icon">
          {uploading ? (
            <IconLoader size={28} className="icon-spin" />
          ) : isDragActive ? (
            <IconDownload size={28} className="icon-accent" />
          ) : (
            <IconUpload size={28} className="icon-muted" />
          )}
        </span>
        <p className="dropzone-text">
          {uploading ? 'Processing...' : isDragActive ? 'Drop here' : <><strong>Drop a file</strong> or click</>}
        </p>
        <p className="dropzone-hint">PDF or TXT — up to 50 MB</p>
      </div>
      {uploading && (
        <div className="upload-progress">
          <div className="progress-bar-track">
            <div className="progress-bar-fill" style={{ width: `${progress}%` }} />
          </div>
          <p className="progress-label">{progress}%</p>
        </div>
      )}
    </div>
  );
}
