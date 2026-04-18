import React, { useState } from 'react';
import { Search } from 'lucide-react';
import { NODE_LIBRARY } from '../../constants/nodeLibrary';
import CategorySection from './CategorySection';

interface NodeSidebarProps {
  onClose?: () => void;
  onSelect?: (type: string) => void;
}

const NodeSidebar: React.FC<NodeSidebarProps> = ({ onClose, onSelect }) => {
  const [searchTerm, setSearchTerm] = useState('');

  const filterNodes = (nodes: any[]) => {
    if (!searchTerm) return nodes;
    return nodes.filter(node => 
      node.label.toLowerCase().includes(searchTerm.toLowerCase()) ||
      node.description.toLowerCase().includes(searchTerm.toLowerCase()) ||
      node.type.toLowerCase().includes(searchTerm.toLowerCase())
    );
  };

  const categories = [
    { title: 'Triggers', id: 'trigger', nodes: NODE_LIBRARY.trigger },
    { title: 'Input & Output', id: 'input_output', nodes: NODE_LIBRARY.input_output },
    { title: 'Actions', id: 'action', nodes: NODE_LIBRARY.action },
    { title: 'Data Transformation', id: 'transform', nodes: NODE_LIBRARY.transform },
    { title: 'AI', id: 'ai', nodes: NODE_LIBRARY.ai },
  ];

  return (
    <aside className="w-80 bg-white dark:bg-slate-900 overflow-y-auto h-full p-5 flex flex-col gap-6 transition-colors duration-300">
      <div className="flex flex-col gap-4">
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

        {/* Search Bar */}
        <div className="relative group">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 group-focus-within:text-blue-500 transition-colors" />
          <input
            type="text"
            placeholder="Search nodes..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all text-slate-700 dark:text-slate-200"
          />
        </div>
      </div>

      <div className="flex flex-col gap-6">
        {categories.map(cat => {
          const filtered = filterNodes(cat.nodes);
          if (filtered.length === 0) return null;
          
          return (
            <CategorySection
              key={cat.id}
              title={cat.title}
              category={cat.id as any}
              nodes={filtered}
              onSelect={onSelect}
            />
          );
        })}
        
        {searchTerm && categories.every(cat => filterNodes(cat.nodes).length === 0) && (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="w-12 h-12 bg-slate-50 dark:bg-slate-800 rounded-full flex items-center justify-center mb-4">
              <Search className="w-6 h-6 text-slate-300 dark:text-slate-700" />
            </div>
            <p className="text-sm font-medium text-slate-500 dark:text-slate-400">No nodes found</p>
            <button 
              onClick={() => setSearchTerm('')}
              className="mt-2 text-xs font-bold text-blue-500 hover:text-blue-600 uppercase tracking-wider"
            >
              Clear Search
            </button>
          </div>
        )}
      </div>
    </aside>
  );
};

export default NodeSidebar;
