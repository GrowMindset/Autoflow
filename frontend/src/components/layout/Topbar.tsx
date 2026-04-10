import React, { useState, useEffect, useRef } from 'react';
import { User, LogOut, ChevronDown, Settings, CreditCard, Shield, Download, Upload } from 'lucide-react';
import { useAuthStore } from '../../store/authStore';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import ImportModal from './ImportModal';

interface TopbarProps {
  workflowName: string;
  workflowDescription: string;
  onRename: (newName: string) => void;
  onDescribeWorkflow: (desc: string) => void;
  onToggleNodePalette: () => void;
  isNodePaletteOpen: boolean;
  onSave: () => void;
  onImport: (data: any) => void;
  isPublished?: boolean;
  onTogglePublish?: () => void;
  saveStatus?: 'idle' | 'saving' | 'saved' | 'error';
}

const Topbar: React.FC<TopbarProps> = ({
  workflowName,
  workflowDescription,
  onRename,
  onDescribeWorkflow,
  onToggleNodePalette,
  isNodePaletteOpen,
  onSave,
  onImport,
  isPublished = false,
  onTogglePublish,
  saveStatus = 'idle'
}) => {
  const [isEditing, setIsEditing] = useState(false);
  const [tempName, setTempName] = useState(workflowName);
  const [isEditingDesc, setIsEditingDesc] = useState(false);
  const [tempDesc, setTempDesc] = useState(workflowDescription);
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const descRef = useRef<HTMLInputElement>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const user = useAuthStore((state) => state.user);
  const clearAuth = useAuthStore((state) => state.clearAuth);
  const navigate = useNavigate();

  useEffect(() => {
    setTempName(workflowName);
  }, [workflowName]);

  useEffect(() => {
    setTempDesc(workflowDescription);
  }, [workflowDescription]);

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  useEffect(() => {
    if (isEditingDesc && descRef.current) {
      descRef.current.focus();
      descRef.current.select();
    }
  }, [isEditingDesc]);

  // Handle clicks outside user menu to close it
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (userMenuRef.current && !userMenuRef.current.contains(event.target as Node)) {
        setIsUserMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleBlur = () => {
    setIsEditing(false);
    if (tempName.trim()) {
      onRename(tempName.trim());
    } else {
      setTempName(workflowName);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleBlur();
    if (e.key === 'Escape') {
      setTempName(workflowName);
      setIsEditing(false);
    }
  };

  const handleDescBlur = () => {
    setIsEditingDesc(false);
    onDescribeWorkflow(tempDesc.trim());
  };

  const handleDescKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleDescBlur();
    if (e.key === 'Escape') {
      setTempDesc(workflowDescription);
      setIsEditingDesc(false);
    }
  };

  const handleLogout = () => {
    clearAuth();
    toast.success('Logged out successfully');
    navigate('/login');
  };

  const handleExport = () => {
    if ((window as any).getCanvasWorkflowData) {
      const data = (window as any).getCanvasWorkflowData(workflowName);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const win = window.open(url, '_blank');
      if (win) {
        toast.success('Workflow JSON opened in new tab');
      } else {
        toast.error('Pop-up blocked! Please allow pop-ups to export.');
      }
    }
  };

  return (
    <header className="h-14 bg-white border-b border-slate-200 flex items-center px-6 sticky top-0 z-40">
      <div className="flex-1 flex flex-col justify-center gap-0">
        {/* Workflow Name */}
        {isEditing ? (
          <input
            ref={inputRef}
            type="text"
            className="text-sm font-bold text-slate-800 bg-slate-50 border-b-2 border-blue-500 outline-none px-2 py-0.5 w-fit max-w-xs"
            value={tempName}
            onChange={(e) => setTempName(e.target.value)}
            onBlur={handleBlur}
            onKeyDown={handleKeyDown}
          />
        ) : (
          <div
            className="flex items-center gap-1.5 group cursor-pointer hover:bg-slate-50 rounded px-2 py-0.5 transition-colors w-fit"
            onClick={() => setIsEditing(true)}
          >
            <h2 className="text-sm font-bold text-slate-800 tracking-tight leading-none">{workflowName}</h2>
            <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-slate-300 group-hover:text-slate-400 opacity-0 group-hover:opacity-100 transition-opacity"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/><path d="m15 5 4 4"/></svg>
          </div>
        )}

        {/* Workflow Description */}
        {isEditingDesc ? (
          <input
            ref={descRef}
            type="text"
            placeholder="Add a description..."
            className="text-[10px] text-slate-500 bg-transparent border-b border-blue-400 outline-none px-2 py-0 w-64 leading-tight"
            value={tempDesc}
            onChange={(e) => setTempDesc(e.target.value)}
            onBlur={handleDescBlur}
            onKeyDown={handleDescKeyDown}
          />
        ) : (
          <div
            className="flex items-center gap-1 group/desc cursor-pointer px-2 hover:opacity-80 transition-opacity w-fit"
            onClick={() => setIsEditingDesc(true)}
            title="Click to edit description"
          >
            <span className={`text-[10px] leading-tight truncate max-w-[280px] ${
              workflowDescription ? 'text-slate-400' : 'text-slate-300 italic'
            }`}>
              {workflowDescription || 'Add a description...'}
            </span>
            <svg xmlns="http://www.w3.org/2000/svg" width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" className="text-slate-300 opacity-0 group-hover/desc:opacity-100 transition-opacity flex-shrink-0"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/><path d="m15 5 4 4"/></svg>
          </div>
        )}
      </div>

      <div className="flex items-center gap-2 mr-6 border-r border-slate-100 pr-6">
        <button
          onClick={onToggleNodePalette}
          className={`flex items-center gap-2 px-4 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-[0.1em] transition-all border ${
            isNodePaletteOpen
              ? 'bg-slate-900 text-white border-slate-900 shadow-lg shadow-slate-200'
              : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
          }`}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="3"
            strokeLinecap="round"
            strokeLinejoin="round"
            className={`transition-transform duration-300 ${isNodePaletteOpen ? 'rotate-45 text-red-400' : ''}`}
          >
            <path d="M12 5v14"/><path d="M5 12h14"/>
          </svg>
          {isNodePaletteOpen ? 'Close Nodes' : 'Add Node'}
        </button>

        <div className="flex items-center gap-3 mr-4">
          {saveStatus === 'saving' && (
            <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-blue-50/50">
              <div className="w-3 h-3 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
              <span className="text-[9px] font-black uppercase tracking-widest text-blue-500">Saving</span>
            </div>
          )}
          {saveStatus === 'saved' && (
            <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-emerald-50/50">
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" className="text-emerald-500"><path d="M20 6 9 17l-5-5"/></svg>
              <span className="text-[9px] font-black uppercase tracking-widest text-emerald-500">Saved</span>
            </div>
          )}
          {saveStatus === 'error' && (
            <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-red-50/50">
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" className="text-red-500"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              <span className="text-[9px] font-black uppercase tracking-widest text-red-500">Error</span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-1.5 mr-4 border-r border-slate-100 pr-4">
          <button
            onClick={() => setIsImportModalOpen(true)}
            className="p-1.5 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-all group relative"
            title="Import Workflow"
          >
            <Download size={14} strokeWidth={3} />
            <span className="absolute -bottom-8 left-1/2 -translate-x-1/2 px-2 py-1 bg-slate-900 text-white text-[9px] font-black uppercase tracking-widest rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap z-50 shadow-xl">Import</span>
          </button>

          <button
            onClick={handleExport}
            className="p-1.5 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-all group relative"
            title="Export Workflow"
          >
            <Upload size={14} strokeWidth={3} />
            <span className="absolute -bottom-8 left-1/2 -translate-x-1/2 px-2 py-1 bg-slate-900 text-white text-[9px] font-black uppercase tracking-widest rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap z-50 shadow-xl">Export</span>
          </button>
        </div>

        {isImportModalOpen && (
          <ImportModal 
            onClose={() => setIsImportModalOpen(false)} 
            onImport={onImport} 
          />
        )}

        <button
          onClick={onSave}
          disabled={saveStatus === 'saving'}
          className={`${
            saveStatus === 'saving' ? 'bg-slate-100 text-slate-400 border-slate-200 cursor-not-allowed shadow-none' : 'bg-blue-600 hover:bg-blue-700 text-white shadow-lg shadow-blue-500/20'
          } px-5 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-[0.1em] transition-all active:scale-95`}
        >
          {saveStatus === 'saving' ? 'Saving...' : 'Save Changes'}
        </button>

        <button
          onClick={onTogglePublish}
          className={`px-5 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-[0.1em] transition-all active:scale-95 flex items-center gap-2 ${
            isPublished
              ? 'bg-slate-100 text-slate-600 border border-slate-200 hover:bg-slate-200'
              : 'bg-emerald-500 hover:bg-emerald-600 text-white shadow-lg shadow-emerald-500/20'
          }`}
        >
          <div className={`w-2 h-2 rounded-full ${isPublished ? 'bg-emerald-500 animate-pulse' : 'bg-white/50'}`} />
          {isPublished ? 'Unpublish' : 'Publish'}
        </button>
      </div>

      <div className="flex items-center gap-4 relative" ref={userMenuRef}>
        <div className="hidden xl:flex flex-col items-end text-right mr-1">
          <span className="text-xs font-black text-slate-800 leading-none">{user?.username}</span>
        </div>

        <button
          onClick={() => setIsUserMenuOpen(!isUserMenuOpen)}
          className={`flex items-center gap-2 p-1 rounded-xl transition-all border ${
            isUserMenuOpen ? 'bg-slate-50 border-slate-200' : 'bg-transparent border-transparent hover:bg-slate-50'
          }`}
        >
          <div className="w-8 h-8 bg-gradient-to-tr from-blue-500 to-purple-600 rounded-lg flex items-center justify-center text-white text-sm font-black shadow-md">
            {user?.username?.substring(0, 1).toUpperCase() || <User size={16} />}
          </div>
          <ChevronDown size={14} className={`text-slate-400 transition-transform duration-300 ${isUserMenuOpen ? 'rotate-180' : ''}`} />
        </button>

        {isUserMenuOpen && (
          <div className="absolute top-12 right-0 w-64 bg-white border border-slate-200 rounded-2xl shadow-[0_20px_50px_rgba(0,0,0,0.15)] overflow-hidden animate-in fade-in zoom-in-95 duration-200 py-2">
            <div className="px-4 py-3 border-b border-slate-50 mb-1 flex flex-col gap-1">
              <p className="text-xs font-black text-slate-800 tracking-tight leading-none">{user?.username}</p>
              <p className="text-[10px] font-bold text-slate-400 truncate">{user?.email}</p>
              <div className="h-2" />
              <p className="text-[9px] font-black text-slate-300 uppercase tracking-widest leading-none">Account Settings</p>
            </div>

            <button className="w-full flex items-center gap-3 px-4 py-2.5 text-slate-600 hover:bg-slate-50 hover:text-blue-600 transition-all text-sm font-bold">
              <div className="w-8 h-8 rounded-lg bg-slate-50 flex items-center justify-center">
                <Settings size={16} />
              </div>
              Preferences
            </button>

            <button className="w-full flex items-center gap-3 px-4 py-2.5 text-slate-600 hover:bg-slate-50 hover:text-blue-600 transition-all text-sm font-bold">
              <div className="w-8 h-8 rounded-lg bg-slate-50 flex items-center justify-center">
                <CreditCard size={16} />
              </div>
              Billing
            </button>

            <button className="w-full flex items-center gap-3 px-4 py-2.5 text-slate-600 hover:bg-slate-50 hover:text-blue-600 transition-all text-sm font-bold">
              <div className="w-8 h-8 rounded-lg bg-slate-50 flex items-center justify-center">
                <Shield size={16} />
              </div>
              API Keys
            </button>

            <div className="h-px bg-slate-100 my-1 mx-2"></div>

            <button
              onClick={handleLogout}
              className="w-full flex items-center gap-3 px-4 py-2.5 text-red-500 hover:bg-red-50 transition-all text-sm font-black mt-1"
            >
              <div className="w-8 h-8 rounded-lg bg-red-50 flex items-center justify-center">
                <LogOut size={16} />
              </div>
              Sign Out
            </button>
          </div>
        )}
      </div>
    </header>
  );
};

export default Topbar;
