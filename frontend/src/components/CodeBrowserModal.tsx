import { useState, useRef, useEffect } from 'react';
import type { CodeBrowserSelection } from '../types';
import { FileListPanel } from './FileListPanel';
import { CodeViewerPanel } from './CodeViewerPanel';

interface Props {
  projectId: string;
  onSelect: (selection: CodeBrowserSelection) => void;
  onCancel: () => void;
}

export function CodeBrowserModal({ projectId, onSelect, onCancel }: Props) {
  const [step, setStep] = useState<'file-list' | 'code-viewer'>('file-list');
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const modalRef = useRef<HTMLDivElement>(null);

  // Focus modal on mount
  useEffect(() => {
    modalRef.current?.focus();
  }, []);

  const handleSelectFile = (path: string) => {
    setSelectedFile(path);
    setStep('code-viewer');
  };

  const handleBack = () => {
    setStep('file-list');
    setSelectedFile(null);
  };

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: 'rgba(0,0,0,0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}
      onClick={onCancel}
    >
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        tabIndex={-1}
        style={{
          background: 'white',
          borderRadius: 8,
          padding: 24,
          width: '90%',
          maxWidth: 900,
          height: '80vh',
          display: 'flex',
          flexDirection: 'column',
          outline: 'none',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {step === 'file-list' && (
          <FileListPanel
            projectId={projectId}
            onSelectFile={handleSelectFile}
            onCancel={onCancel}
          />
        )}

        {step === 'code-viewer' && selectedFile && (
          <CodeViewerPanel
            projectId={projectId}
            filePath={selectedFile}
            onBack={handleBack}
            onSelect={onSelect}
            onCancel={onCancel}
          />
        )}
      </div>
    </div>
  );
}
