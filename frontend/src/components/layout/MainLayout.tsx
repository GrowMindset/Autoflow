import React, { useState, useCallback, useEffect } from 'react';
import toast from 'react-hot-toast';
import Topbar from './Topbar';
import NodeSidebar from '../sidebar/NodeSidebar';
import WorkflowSidebar from '../sidebar/WorkflowSidebar';
import WorkflowCanvas from '../canvas/WorkflowCanvas';
import { workflowService } from '../../services/workflowService';

interface Workflow {
  id: string;
  name: string;
}

const MainLayout: React.FC = () => {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [currentWorkflowId, setCurrentWorkflowId] = useState<string>('');
  const [isLoading, setIsLoading] = useState(true);
  const [isLeftSidebarCollapsed, setIsLeftSidebarCollapsed] = useState(false);
  const [isRightSidebarOpen, setIsRightSidebarOpen] = useState(false);
  
  // Initial fetch
  useEffect(() => {
    const fetchWorkflows = async () => {
      setIsLoading(true);
      try {
        const data = await workflowService.getWorkflows();
        setWorkflows(data);
        if (data.length > 0) {
          setCurrentWorkflowId(data[0].id);
        }
      } catch (error) {
        console.error('Failed to load workflows');
      } finally {
        setIsLoading(false);
      }
    };
    fetchWorkflows();
  }, []);

  const currentWorkflow = workflows.find(w => w.id === currentWorkflowId) || workflows[0] || { id: 'new', name: 'Untitled Workflow' };

  const onNewWorkflow = useCallback(() => {
    // For new workflows, we just reset the canvas. 
    // They will get an ID once saved to the backend.
    setCurrentWorkflowId('new');
    if ((window as any).loadCanvasWorkflowData) {
        (window as any).loadCanvasWorkflowData({ nodes: [], edges: [] });
    }
  }, []);

  const onRenameWorkflow = useCallback((id: string, newName: string) => {
    setWorkflows(prev => prev.map(w => w.id === id ? { ...w, name: newName } : w));
  }, []);

  const onSelectWorkflow = useCallback(async (id: string) => {
    if (id === 'new') {
        onNewWorkflow();
        return;
    }

    setCurrentWorkflowId(id);
    setIsLoading(true);
    try {
        const fullWorkflow = await workflowService.getWorkflow(id);
        if (fullWorkflow && (window as any).loadCanvasWorkflowData) {
            (window as any).loadCanvasWorkflowData(fullWorkflow.definition);
        }
    } finally {
        setIsLoading(false);
    }
  }, [onNewWorkflow]);

  const handleSave = useCallback(async () => {
    if (!(window as any).getCanvasWorkflowData) return;

    const workflowData = (window as any).getCanvasWorkflowData(currentWorkflow.name);
    const savePayload = {
      ...workflowData,
      id: currentWorkflowId === 'new' ? undefined : currentWorkflowId
    };
    const { name, definition } = savePayload;

    // 1. Validation: Content (prevent completely empty flows)
    if (definition.nodes.length === 0) {
      toast.error('Cannot save an empty workflow');
      return;
    }

    // 4. Execution with Toast feedback
    try {
      const savedResult = await toast.promise(
        workflowService.saveWorkflow(savePayload),
        {
          loading: 'Saving workflow...',
          success: <b>Workflow saved successfully!</b>,
          error: <b>Could not save workflow.</b>,
        }
      );
      
      // Update workflows list
      const updatedWorkflows = await workflowService.getWorkflows();
      setWorkflows(updatedWorkflows);
      
      // If it was a new workflow, switch to the newly created ID
      if (currentWorkflowId === 'new' && savedResult.id) {
          setCurrentWorkflowId(savedResult.id);
      }
      
      console.log('--- SAVED DATA ---', savedResult);
    } catch (error) {
      console.error('Save failed:', error);
    }
  }, [currentWorkflow.name, currentWorkflowId]);

  return (
    <div className="flex h-screen overflow-hidden bg-white font-sans antialiased text-slate-900">
      {isLoading && (
        <div className="absolute inset-0 z-[9999] bg-white/50 backdrop-blur-sm flex items-center justify-center">
          <div className="flex flex-col items-center gap-4">
            <div className="w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
            <p className="text-sm font-bold text-slate-500 animate-pulse uppercase tracking-widest">Loading Workflow...</p>
          </div>
        </div>
      )}

      {/* Workflow Navigation (Left Sidebar) */}
      <WorkflowSidebar 
        workflows={workflows}
        currentWorkflowId={currentWorkflowId}
        onSelectWorkflow={onSelectWorkflow}
        onNewWorkflow={onNewWorkflow}
        isCollapsed={isLeftSidebarCollapsed}
        onToggleCollapse={() => setIsLeftSidebarCollapsed(!isLeftSidebarCollapsed)}
      />

      <div className="flex-1 flex flex-col min-w-0 relative">
        {/* Topbar with Editable Title */}
        <Topbar 
          workflowName={currentWorkflow.name}
          onRename={(newName) => onRenameWorkflow(currentWorkflow.id, newName)}
          onToggleNodePalette={() => setIsRightSidebarOpen(!isRightSidebarOpen)} 
          isNodePaletteOpen={isRightSidebarOpen}
          onNewWorkflow={onNewWorkflow}
          onSave={handleSave}
        />

        <div className="flex-1 flex overflow-hidden">
          {/* Main Canvas Area */}
          <main className="flex-1 overflow-hidden relative">
            <WorkflowCanvas key={currentWorkflowId} workflowId={currentWorkflowId} />
          </main>

          {/* Node Palette (Right Sidebar) - Now a push-sidebar */}
          <div 
            className={`h-full border-l border-slate-200 bg-white transition-all duration-300 ease-in-out overflow-hidden flex-shrink-0 ${
              isRightSidebarOpen ? 'w-[320px] opacity-100' : 'w-0 opacity-0 border-none'
            }`}
          >
            <div className="w-[320px] h-full overflow-hidden">
              <NodeSidebar />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default MainLayout;
