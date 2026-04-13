import React from 'react';
import { NODE_LIBRARY } from '../../constants/nodeLibrary';
import CategorySection from './CategorySection';

interface NodeSidebarProps {
  onClose?: () => void;
}

const NodeSidebar: React.FC<NodeSidebarProps> = ({ onClose }) => {
  return (
    <aside className="w-80 bg-white dark:bg-slate-900 overflow-y-auto h-full p-5 flex flex-col gap-6 transition-colors duration-300">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />
          <h2 className="text-sm font-bold uppercase tracking-widest text-slate-400 dark:text-slate-400">Node Palette</h2>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="p-2 rounded-md text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            title="Close"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        )}
      </div>

      <div className="flex flex-col gap-6">
        <CategorySection
          title="Triggers"
          category="trigger"
          nodes={NODE_LIBRARY.trigger}
        />
        <CategorySection
          title="Actions"
          category="action"
          nodes={NODE_LIBRARY.action}
        />
        <CategorySection
          title="Data Transform"
          category="transform"
          nodes={NODE_LIBRARY.transform}
        />
        <CategorySection
          title="AI"
          category="ai"
          nodes={NODE_LIBRARY.ai}
        />
      </div>
    </aside>
  );
};

export default NodeSidebar;
