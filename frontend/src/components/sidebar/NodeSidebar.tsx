import React, { useState } from 'react';
import { Search } from 'lucide-react';
import { NODE_LIBRARY, NodeDefinition } from '../../constants/nodeLibrary';
import CategorySection from './CategorySection';
import NodeItem from './NodeItem';

interface NodeSidebarProps {
  onClose?: () => void;
  onSelect?: (type: string) => void;
}

const NodeSidebar: React.FC<NodeSidebarProps> = ({ onClose, onSelect }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [openActionGroups, setOpenActionGroups] = useState<Record<string, boolean>>({});
  const normalizedSearch = searchTerm.trim().toLowerCase();

  const filterNodes = (nodes: NodeDefinition[]) => {
    if (!normalizedSearch) return nodes;
    return nodes.filter((node) =>
      node.label.toLowerCase().includes(normalizedSearch) ||
      node.description.toLowerCase().includes(normalizedSearch) ||
      node.type.toLowerCase().includes(normalizedSearch)
    );
  };

  const actionGroups = [
    { id: 'mail', title: 'Mail', types: ['get_gmail_message', 'send_gmail_message', 'create_gmail_draft', 'add_gmail_label'] },
    { id: 'google_sheets', title: 'Google Sheets', types: ['create_google_sheets', 'read_google_sheets', 'search_update_google_sheets'] },
    { id: 'google_docs', title: 'Google Docs', types: ['create_google_docs', 'read_google_docs', 'update_google_docs'] },
    { id: 'telegram', title: 'Telegram', types: ['telegram'] },
    { id: 'whatsapp', title: 'WhatsApp', types: ['whatsapp'] },
    { id: 'slack', title: 'Slack', types: ['slack_send_message'] },
    { id: 'linkedin', title: 'LinkedIn', types: ['linkedin'] },
    { id: 'workflow_control', title: 'Workflow Control', types: ['execute_workflow'] },
  ];

  const groupedActionTypes = new Set(actionGroups.flatMap((group) => group.types));
  const filteredActionGroups = actionGroups
    .map((group) => ({
      ...group,
      nodes: filterNodes(NODE_LIBRARY.action.filter((node) => group.types.includes(node.type))),
    }))
    .filter((group) => group.nodes.length > 0);

  const otherActionNodes = filterNodes(
    NODE_LIBRARY.action.filter((node) => !groupedActionTypes.has(node.type))
  );

  const actionSections = [
    ...filteredActionGroups,
    ...(otherActionNodes.length > 0 ? [{ id: 'other', title: 'Other', nodes: otherActionNodes }] : []),
  ];

  const categories = [
    { title: 'Triggers', id: 'trigger', nodes: NODE_LIBRARY.trigger },
    { title: 'Input & Output', id: 'input_output', nodes: NODE_LIBRARY.input_output },
    { title: 'Data Transformation', id: 'transform', nodes: NODE_LIBRARY.transform },
    { title: 'Utility', id: 'utility', nodes: NODE_LIBRARY.utility },
    { title: 'AI', id: 'ai', nodes: NODE_LIBRARY.ai },
  ];

  const hasActionResults = actionSections.length > 0;
  const hasCategoryResults = categories.some((cat) => filterNodes(cat.nodes).length > 0);
  const hasAnyResults = hasActionResults || hasCategoryResults;

  const toggleActionGroup = (groupId: string) => {
    setOpenActionGroups((prev) => ({ ...prev, [groupId]: !prev[groupId] }));
  };

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
        {hasActionResults && (
          <CategorySection
            title="Actions"
            category="action"
            nodes={[]}
            isOpenDefault
            customContent={
              <div className="flex flex-col gap-1">
                {actionSections.map((group) => {
                  const isGroupOpen = normalizedSearch ? true : Boolean(openActionGroups[group.id]);
                  return (
                    <div key={group.id} className="flex flex-col gap-1">
                      <button
                        onClick={() => toggleActionGroup(group.id)}
                        className="flex items-center justify-between p-2 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-800 transition-all group"
                      >
                        <div className="flex items-center gap-3">
                          <div className="w-1.5 h-1.5 rounded-full bg-blue-500" />
                          <span className="text-[10px] font-bold uppercase tracking-widest text-slate-500 dark:text-slate-300">
                            {group.title}
                          </span>
                        </div>
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          width="14"
                          height="14"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="2.5"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          className={`text-slate-300 dark:text-slate-700 transition-transform duration-200 ${isGroupOpen ? 'rotate-180' : ''}`}
                        >
                          <path d="m6 9 6 6 6-6" />
                        </svg>
                      </button>

                      {isGroupOpen && (
                        <div className="flex flex-col gap-1.5 pl-4 py-1 animate-in slide-in-from-top-1 duration-200">
                          {group.nodes.map((node) => (
                            <NodeItem key={node.type} node={node} onSelect={onSelect} />
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            }
          />
        )}

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
        
        {searchTerm && !hasAnyResults && (
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
