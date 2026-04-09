import React, { useState, useEffect, useRef } from 'react';
import { User, LogOut, ChevronDown, Settings, CreditCard, Shield } from 'lucide-react';
import { useAuthStore } from '../../store/authStore';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';

interface TopbarProps {
  workflowName: string;
  onRename: (newName: string) => void;
  onToggleNodePalette: () => void;
  isNodePaletteOpen: boolean;
  onNewWorkflow: () => void;
  onSave: () => void;
}

const Topbar: React.FC<TopbarProps> = ({ 
  workflowName, 
  onRename, 
  onToggleNodePalette, 
  isNodePaletteOpen,
  onNewWorkflow,
  onSave 
}) => {
  const [isEditing, setIsEditing] = useState(false);
  const [tempName, setTempName] = useState(workflowName);
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);
  
  const user = useAuthStore((state) => state.user);
  const clearAuth = useAuthStore((state) => state.clearAuth);
  const navigate = useNavigate();

  useEffect(() => {
    setTempName(workflowName);
  }, [workflowName]);

  useEffect(() => {
    if (isEditing && inputRef.current) {
        inputRef.current.focus();
        inputRef.current.select();
    }
  }, [isEditing]);

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

  const handleLogout = () => {
    clearAuth();
    toast.success('Logged out successfully');
    navigate('/login');
  };

  return (
    <header className="h-14 bg-white border-b border-slate-200 flex items-center px-6 sticky top-0 z-40">
      <div className="flex-1 flex items-center gap-1">
        {isEditing ? (
          <input
            ref={inputRef}
            type="text"
            className="text-base font-bold text-slate-800 bg-slate-50 border-b-2 border-blue-500 outline-none px-2 py-0.5"
            value={tempName}
            onChange={(e) => setTempName(e.target.value)}
            onBlur={handleBlur}
            onKeyDown={handleKeyDown}
          />
        ) : (
          <div 
            className="flex items-center gap-2 group cursor-pointer px-2 py-1 hover:bg-slate-50 rounded transition-colors"
            onClick={() => setIsEditing(true)}
          >
            <h2 className="text-base font-bold text-slate-800 tracking-tight">{workflowName}</h2>
            <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-slate-300 group-hover:text-slate-400 opacity-0 group-hover:opacity-100 transition-opacity"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/><path d="m15 5 4 4"/></svg>
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

        <button 
           onClick={onNewWorkflow}
           className="px-4 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-[0.1em] bg-white text-slate-600 hover:bg-slate-50 border border-slate-200 transition-all active:scale-95"
        >
            New Flow
        </button>

        <button 
          onClick={onSave}
          className="bg-blue-600 hover:bg-blue-700 text-white px-5 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-[0.1em] transition-all active:scale-95 shadow-lg shadow-blue-500/20"
        >
          Save Changes
        </button>
      </div>

      <div className="flex items-center gap-4 relative" ref={userMenuRef}>
        <div className="hidden xl:flex flex-col items-end text-right mr-1">
          <span className="text-xs font-black text-slate-800 leading-none">{user?.username}</span>
          <span className="text-[9px] font-bold text-slate-400 uppercase tracking-widest mt-1">{user?.email}</span>
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
            <div className="px-4 py-3 border-b border-slate-50 mb-1">
              <p className="text-xs font-black text-slate-400 uppercase tracking-widest leading-none">Account Settings</p>
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
