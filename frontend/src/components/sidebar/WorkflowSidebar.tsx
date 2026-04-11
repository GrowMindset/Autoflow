import React, { useState } from 'react';
import { createPortal } from 'react-dom';

interface Workflow {
  id: string;
  name: string;
  updated_at?: string;
}

interface WorkflowSidebarProps {
  workflows: Workflow[];
  currentWorkflowId: string;
  onSelectWorkflow: (id: string) => void;
  onNewWorkflow: () => void;
  onDeleteWorkflow: (id: string) => Promise<void>;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
}

// ── Confirmation Dialog ────────────────────────────────────────────────────────
interface ConfirmDeleteProps {
  workflowName: string;
  onConfirm: () => void;
  onCancel: () => void;
  isDeleting: boolean;
}

const ConfirmDeleteDialog: React.FC<ConfirmDeleteProps> = ({ workflowName, onConfirm, onCancel, isDeleting }) => {
  return createPortal(
    <div className="fixed inset-0 z-[99999] flex items-center justify-center p-4 bg-slate-900/50 dark:bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-150">
      <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-[0_30px_80px_rgba(0,0,0,0.25)] border border-slate-100 dark:border-slate-800 w-full max-w-sm animate-in zoom-in-95 duration-200">
        <div className="p-6 pb-4">
          <div className="flex items-center gap-4 mb-4">
            <div className="w-11 h-11 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-100 dark:border-red-900/30 flex items-center justify-center flex-shrink-0">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-red-500">
                <polyline points="3 6 5 6 21 6" />
                <path d="m19 6-.867 12.142A2 2 0 0 1 16.138 20H7.862a2 2 0 0 1-1.995-1.858L5 6" />
                <path d="M10 11v6" />
                <path d="M14 11v6" />
                <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
              </svg>
            </div>
            <div>
              <h3 className="text-base font-black text-slate-800 dark:text-slate-100">Delete Workflow?</h3>
              <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">This action cannot be undone.</p>
            </div>
          </div>
          <div className="bg-slate-50 dark:bg-slate-800/50 rounded-xl px-4 py-3 border border-slate-100 dark:border-slate-800">
            <p className="text-sm text-slate-600 dark:text-slate-400 font-medium">
              You are about to permanently delete{' '}
              <span className="font-black text-slate-800 dark:text-slate-100">"{workflowName}"</span>{' '}
              and all its data.
            </p>
          </div>
        </div>

        <div className="px-6 pb-6 flex items-center gap-3">
          <button
            id="cancel-delete-btn"
            onClick={onCancel}
            disabled={isDeleting}
            className="flex-1 px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 text-sm font-bold text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800 transition-all disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            id="confirm-delete-btn"
            onClick={onConfirm}
            disabled={isDeleting}
            className="flex-1 px-4 py-2.5 rounded-xl bg-red-500 hover:bg-red-600 text-white text-sm font-black transition-all shadow-lg shadow-red-200 active:scale-95 disabled:opacity-60 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {isDeleting ? (
              <>
                <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                Deleting...
              </>
            ) : (
              'Delete Workflow'
            )}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
};

// ── Main Component ─────────────────────────────────────────────────────────────
const WorkflowSidebar: React.FC<WorkflowSidebarProps> = ({
  workflows,
  currentWorkflowId,
  onSelectWorkflow,
  onNewWorkflow,
  onDeleteWorkflow,
  isCollapsed,
  onToggleCollapse,
}) => {
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const pendingWorkflow = workflows.find(w => w.id === pendingDeleteId);

  const handleConfirmDelete = async () => {
    if (!pendingDeleteId) return;
    setIsDeleting(true);
    try {
      await onDeleteWorkflow(pendingDeleteId);
    } finally {
      setIsDeleting(false);
      setPendingDeleteId(null);
    }
  };

  return (
    <>
      {pendingWorkflow && (
        <ConfirmDeleteDialog
          workflowName={pendingWorkflow.name}
          onConfirm={handleConfirmDelete}
          onCancel={() => setPendingDeleteId(null)}
          isDeleting={isDeleting}
        />
      )}

      <aside
        className={`h-screen bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 transition-all duration-300 ease-in-out flex flex-col relative z-50 ${isCollapsed ? 'w-[68px]' : 'w-72'
          }`}
      >
        {/* Sidebar Header / Brand */}
        <div className={`p-4 flex items-center gap-4 ${isCollapsed ? 'justify-center' : 'p-6'}`}>
          <div className="w-10 h-10 bg-blue-600 rounded-xl flex-shrink-0 flex items-center justify-center shadow-sm overflow-hidden">
            <img src="/logo.png" alt="Autoflow Logo" className="w-full h-full object-cover shadow-inner" />
          </div>
          {!isCollapsed && (
            <div className="overflow-hidden">
              <h1 className="text-base font-bold text-slate-800 dark:text-slate-100 tracking-tight">Autoflow</h1>
              <p className="text-[9px] text-slate-400 dark:text-slate-500 font-bold uppercase tracking-widest leading-none mt-0.5">Automation Engine</p>
            </div>
          )}
        </div>

        {/* Main Navigation */}
        <div className={`flex-1 overflow-y-auto custom-scrollbar flex flex-col gap-8 ${isCollapsed ? 'p-2 mt-4' : 'p-4'}`}>

          {/* Workflows Section */}
          <div className="flex flex-col gap-2">
            {!isCollapsed && (
              <div className="flex items-center justify-between px-2 mb-1">
                <span className="text-[10px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest">My Workflows</span>
                <button
                  onClick={onNewWorkflow}
                  title="Create new workflow"
                  className="w-7 h-7 rounded-lg bg-blue-600 flex items-center justify-center hover:bg-blue-700 transition-all shadow-lg shadow-blue-500/30 active:scale-90 group relative overflow-hidden"
                >
                  <div className="absolute inset-0 bg-white/20 translate-y-full group-hover:translate-y-0 transition-transform duration-300" />
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" className="text-white relative z-10 transition-transform group-hover:rotate-90">
                    <path d="M5 12h14" />
                    <path d="M12 5v14" />
                  </svg>
                </button>
              </div>
            )}

            <div className="flex flex-col gap-1">
              {workflows.map((flow) => (
                <div key={flow.id} className="relative group/item">
                  <button
                    onClick={() => onSelectWorkflow(flow.id)}
                    className={`w-full flex items-center gap-4 transition-all group relative ${currentWorkflowId === flow.id
                      ? 'text-blue-600 shadow-sm bg-blue-50/50 dark:bg-blue-900/10'
                      : 'text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200'
                      } ${isCollapsed ? 'justify-center w-full h-10' : 'p-3 rounded-xl hover:bg-slate-50 dark:hover:bg-slate-800/50'}`}
                  >
                    {currentWorkflowId === flow.id && isCollapsed && (
                      <div className="absolute left-0 w-1 h-5 bg-blue-600 rounded-r-full" />
                    )}

                    <div className={`flex-shrink-0 transition-all ${currentWorkflowId === flow.id
                      ? 'w-2 h-2 rounded-full bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.3)]'
                      : 'w-1.5 h-1.5 rounded-full bg-slate-200 dark:bg-slate-700 group-hover:bg-slate-300 dark:group-hover:bg-slate-600'
                      }`} />

                    {!isCollapsed && (
                      <div className="flex flex-col min-w-0 flex-1 text-left">
                        <span className={`text-sm font-semibold truncate ${currentWorkflowId === flow.id ? 'text-blue-600 dark:text-blue-400' : 'text-slate-600 dark:text-slate-300'}`}>
                          {flow.name}
                        </span>
                        {flow.updated_at && (
                          <span className="text-[10px] text-slate-400 dark:text-slate-500 font-medium truncate mt-0.5">
                            Last saved: {new Date(flow.updated_at).toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                          </span>
                        )}
                      </div>
                    )}
                  </button>

                  {/* Delete Button — appears on row hover, hidden in collapsed mode */}
                  {!isCollapsed && (
                    <button
                      id={`delete-workflow-${flow.id}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        setPendingDeleteId(flow.id);
                      }}
                      title="Delete workflow"
                      className="absolute right-2 top-1/2 -translate-y-1/2 w-6 h-6 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-300 dark:text-slate-600 hover:text-red-500 dark:hover:text-red-400 hover:border-red-200 dark:hover:border-red-900 transition-all flex items-center justify-center opacity-0 group-hover/item:opacity-100 shadow-sm"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="3 6 5 6 21 6" />
                        <path d="m19 6-.867 12.142A2 2 0 0 1 16.138 20H7.862a2 2 0 0 1-1.995-1.858L5 6" />
                        <path d="M10 11v6" />
                        <path d="M14 11v6" />
                        <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
                      </svg>
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* New Workflow Button (Centered in Collapsed) */}
          {isCollapsed && (
            <button
              onClick={onNewWorkflow}
              className="w-12 h-12 rounded-2xl bg-blue-600 text-white flex items-center justify-center hover:bg-blue-700 transition-all shadow-xl shadow-blue-500/40 self-center mt-2 group relative overflow-hidden active:scale-90"
            >
              <div className="absolute inset-0 bg-white/20 translate-y-full group-hover:translate-y-0 transition-transform duration-300" />
              <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" className="relative z-10 transition-transform group-hover:scale-110 group-hover:rotate-90 duration-300">
                <path d="M5 12h14" />
                <path d="M12 5v14" />
              </svg>
            </button>
          )}
        </div>

        {/* Sidebar Footer Toggle */}
        <div className={`p-4 border-t border-slate-100 dark:border-slate-800 flex items-center ${isCollapsed ? 'justify-center h-16' : 'h-16'}`}>
          <button
            onClick={onToggleCollapse}
            className={`group flex items-center gap-3 transition-all ${isCollapsed
              ? 'w-10 h-10 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800 flex items-center justify-center hover:bg-slate-100 dark:hover:bg-slate-800'
              : 'w-full p-2 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300'
              }`}
          >
            <div className={`flex items-center justify-center transition-transform duration-300 ${isCollapsed ? 'rotate-180' : ''}`}>
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-slate-400 dark:text-slate-600">
                <path d="m15 18-6-6 6-6" />
              </svg>
            </div>
            {!isCollapsed && <span className="text-sm font-semibold tracking-tight">Collapse Sidebar</span>}
          </button>
        </div>
      </aside>
    </>
  );
};

export default WorkflowSidebar;
