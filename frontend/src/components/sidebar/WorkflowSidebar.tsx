import React from 'react';

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
  isCollapsed: boolean;
  onToggleCollapse: () => void;
}

const WorkflowSidebar: React.FC<WorkflowSidebarProps> = ({
  workflows,
  currentWorkflowId,
  onSelectWorkflow,
  onNewWorkflow,
  isCollapsed,
  onToggleCollapse,
}) => {
  return (
    <aside 
      className={`h-screen bg-white border-r border-slate-200 transition-all duration-300 ease-in-out flex flex-col relative z-50 ${
        isCollapsed ? 'w-[68px]' : 'w-72'
      }`}
    >
      {/* Sidebar Header / Brand */}
      <div className={`p-4 flex items-center gap-4 ${isCollapsed ? 'justify-center' : 'p-6'}`}>
        <div className="w-10 h-10 bg-blue-600 rounded-xl flex-shrink-0 flex items-center justify-center shadow-sm overflow-hidden">
           <img src="/logo.png" alt="Autoflow Logo" className="w-full h-full object-cover shadow-inner" />
        </div>
        {!isCollapsed && (
          <div className="overflow-hidden">
            <h1 className="text-base font-bold text-slate-800 tracking-tight">Autoflow</h1>
            <p className="text-[9px] text-slate-400 font-bold uppercase tracking-widest leading-none mt-0.5">Automation Engine</p>
          </div>
        )}
      </div>

      {/* Main Navigation */}
      <div className={`flex-1 overflow-y-auto custom-scrollbar flex flex-col gap-8 ${isCollapsed ? 'p-2 mt-4' : 'p-4'}`}>
        
        {/* Workflows Section */}
        <div className="flex flex-col gap-2">
          {!isCollapsed && (
            <div className="flex items-center justify-between px-2 mb-1">
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">My Workflows</span>
              <button 
                onClick={onNewWorkflow}
                className="w-5 h-5 rounded-md bg-slate-50 border border-slate-100 flex items-center justify-center hover:bg-white hover:border-slate-200 transition-colors group"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" className="text-slate-400 group-hover:text-slate-600"><path d="M5 12h14"/><path d="M12 5v14"/></svg>
              </button>
            </div>
          )}

          <div className="flex flex-col gap-1">
            {workflows.map((flow) => (
              <button
                key={flow.id}
                onClick={() => onSelectWorkflow(flow.id)}
                className={`flex items-center gap-4 transition-all group relative ${
                  currentWorkflowId === flow.id 
                    ? 'text-blue-600' 
                    : 'text-slate-500 hover:text-slate-800'
                } ${isCollapsed ? 'justify-center w-full h-10' : 'p-3 rounded-xl hover:bg-slate-50'}`}
              >
                {/* Active Indicator Bar (Collapsed) */}
                {currentWorkflowId === flow.id && isCollapsed && (
                    <div className="absolute left-0 w-1 h-5 bg-blue-600 rounded-r-full" />
                )}

                <div className={`flex-shrink-0 transition-all ${
                   currentWorkflowId === flow.id ? 'w-2 h-2 rounded-full bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.3)]' : 'w-1.5 h-1.5 rounded-full bg-slate-200 group-hover:bg-slate-300'
                }`} />
                
                {!isCollapsed && (
                  <div className="flex flex-col min-w-0">
                    <span className={`text-sm font-semibold truncate ${currentWorkflowId === flow.id ? 'text-blue-600' : 'text-slate-600'}`}>
                      {flow.name}
                    </span>
                    {flow.updated_at && (
                      <span className="text-[10px] text-slate-400 font-medium truncate mt-0.5">
                        Last saved: {new Date(flow.updated_at).toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                      </span>
                    )}
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* New Workflow Button (Centered in Collapsed) */}
        {isCollapsed && (
            <button 
                onClick={onNewWorkflow}
                className="w-10 h-10 rounded-xl border border-slate-200 text-slate-400 flex items-center justify-center hover:bg-slate-50 hover:text-blue-600 transition-all self-center mt-2 group"
            >
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="transition-transform group-hover:scale-110"><path d="M5 12h14"/><path d="M12 5v14"/></svg>
            </button>
        )}
      </div>

      {/* Sidebar Footer Toggle */}
      <div className={`p-4 border-t border-slate-100 flex items-center ${isCollapsed ? 'justify-center h-16' : 'h-16'}`}>
        <button 
          onClick={onToggleCollapse}
          className={`group flex items-center gap-3 transition-all ${
            isCollapsed 
              ? 'w-10 h-10 rounded-xl bg-slate-50 border border-slate-100 flex items-center justify-center hover:bg-slate-100' 
              : 'w-full p-2 rounded-lg hover:bg-slate-50 text-slate-400 hover:text-slate-600'
          }`}
        >
          <div className={`flex items-center justify-center transition-transform duration-300 ${isCollapsed ? 'rotate-180' : ''}`}>
             <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-slate-400">
                <path d="m15 18-6-6 6-6"/>
             </svg>
          </div>
          {!isCollapsed && <span className="text-sm font-semibold tracking-tight">Collapse Sidebar</span>}
        </button>
      </div>
    </aside>
  );
};

export default WorkflowSidebar;
