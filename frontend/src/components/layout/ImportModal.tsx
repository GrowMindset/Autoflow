import React, { useState, useRef } from 'react';
import { createPortal } from 'react-dom';
import { X, FileJson, Upload } from 'lucide-react';
import toast from 'react-hot-toast';

interface ImportModalProps {
  onClose: () => void;
  onImport: (data: any) => void;
}

const ImportModal: React.FC<ImportModalProps> = ({ onClose, onImport }) => {
  const [activeTab, setActiveTab] = useState<'file' | 'paste'>('file');
  const [jsonText, setJsonText] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileImport = (file: File) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const data = JSON.parse(e.target?.result as string);
        onImport(data);
        onClose();
      } catch (err) {
        toast.error('Invalid JSON file format');
      }
    };
    reader.readAsText(file);
  };

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFileImport(file);
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFileImport(file);
  };

  const handlePasteImport = () => {
    if (!jsonText.trim()) {
      toast.error('Please paste your workflow JSON first');
      return;
    }
    try {
      const data = JSON.parse(jsonText);
      onImport(data);
      onClose();
    } catch (err) {
      toast.error('Invalid JSON content. Please check the structure.');
    }
  };

  return createPortal(
    <div className="fixed inset-0 z-[10000] flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-300"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative bg-white w-full max-w-xl rounded-[2rem] shadow-[0_40px_100px_rgba(0,0,0,0.3)] border border-slate-100 overflow-hidden animate-in zoom-in-95 duration-300">

        {/* Header */}
        <div className="px-8 pt-8 pb-6 border-b border-slate-50 flex items-center justify-between">
          <div>
            <h2 className="text-xl font-black text-slate-800 tracking-tight">Import Workflow</h2>
            <p className="text-xs text-slate-400 font-medium mt-1">Bring your logic from another source</p>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-slate-100 rounded-xl transition-all text-slate-400 hover:text-slate-800"
          >
            <X size={20} strokeWidth={2.5} />
          </button>
        </div>

        {/* Tabs */}
        <div className="px-8 py-4 flex gap-2 border-b border-slate-50 bg-slate-50/30">
          <button
            onClick={() => setActiveTab('file')}
            className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl text-xs font-black transition-all ${activeTab === 'file'
              ? 'bg-white text-blue-600 shadow-sm border border-blue-100'
              : 'text-slate-400 hover:text-slate-600 hover:bg-slate-50'
              }`}
          >
            <FileJson size={16} />
            UPLOAD FILE
          </button>
          <button
            onClick={() => setActiveTab('paste')}
            className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl text-xs font-black transition-all ${activeTab === 'paste'
              ? 'bg-white text-blue-600 shadow-sm border border-blue-100'
              : 'text-slate-400 hover:text-slate-600 hover:bg-slate-50'
              }`}
          >
            <ClipboardText size={16} />
            QUICK PASTE
          </button>
        </div>

        {/* Content */}
        <div className="p-8">
          {activeTab === 'file' ? (
            <div
              onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={onDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`group flex flex-col items-center justify-center h-64 rounded-3xl border-2 border-dashed transition-all cursor-pointer ${isDragging
                ? 'bg-blue-50/50 border-blue-400 scale-[1.02]'
                : 'bg-slate-50/50 border-slate-200 hover:bg-slate-50 hover:border-slate-300'
                }`}
            >
              <input
                type="file"
                ref={fileInputRef}
                onChange={onFileChange}
                className="hidden"
                accept=".json"
              />
              <div className="w-16 h-16 rounded-2xl bg-white border border-slate-100 shadow-sm flex items-center justify-center text-slate-400 group-hover:text-blue-500 transition-colors mb-4">
                <Upload size={32} />
              </div>
              <p className="text-sm font-black text-slate-700">Drag & drop your JSON file here</p>
              <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mt-2">or click to browse local files</p>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="relative group">
                <textarea
                  value={jsonText}
                  onChange={(e) => setJsonText(e.target.value)}
                  placeholder='{ "name": "My Workflow", "definition": { ... } }'
                  className="w-full h-64 bg-slate-50 border border-slate-200 rounded-3xl p-6 font-mono text-xs text-slate-700 outline-none focus:border-blue-500 focus:bg-white transition-all resize-none shadow-inner"
                />
                <div className="absolute top-4 right-4 flex gap-2">
                  <div className="px-2 py-1 rounded bg-slate-100 text-slate-400 text-[9px] font-black tracking-widest uppercase">JSON Mode</div>
                </div>
              </div>
              <button
                onClick={handlePasteImport}
                className="w-full bg-slate-900 hover:bg-slate-800 text-white font-black py-4 rounded-2xl text-xs uppercase tracking-widest transition-all active:scale-95 shadow-xl shadow-slate-200"
              >
                Import from Clipboard
              </button>
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
};

// Simple Lucide wrapper replacement to avoid import issues if not available
const ClipboardText = ({ size, className }: { size?: number, className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" width={size || 24} height={size || 24} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className={className}><rect width="8" height="4" x="8" y="2" rx="1" ry="1" /><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" /><path d="M9 14h6" /><path d="M9 10h6" /></svg>
);

export default ImportModal;
