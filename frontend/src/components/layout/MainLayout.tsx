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
  description?: string;
}

const MainLayout: React.FC = () => {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [currentWorkflowId, setCurrentWorkflowId] = useState<string>('');
  const [isLoading, setIsLoading] = useState(true);
  const [isLeftSidebarCollapsed, setIsLeftSidebarCollapsed] = useState(false);
  const [isRightSidebarOpen, setIsRightSidebarOpen] = useState(false);

  // Save Status State
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [currentDescription, setCurrentDescription] = useState<string>('');

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
    // They will get an ID once saved to the backend.
    setCurrentWorkflowId('new');
    setCurrentDescription('');
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
      if (fullWorkflow) {
        setCurrentDescription(fullWorkflow.description || '');
        if ((window as any).loadCanvasWorkflowData) {
          (window as any).loadCanvasWorkflowData(fullWorkflow.definition);
        }
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
      description: currentDescription,
      id: currentWorkflowId === 'new' ? undefined : currentWorkflowId
    };
    const { definition } = savePayload;

    // Validation: prevent completely empty flows
    if (definition.nodes.length === 0) {
      toast.error('Cannot save an empty workflow');
      return;
    }

    // 4. Execution with Toast feedback
    setSaveStatus('saving');
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

      setSaveStatus('saved');
      console.log('--- SAVED DATA ---', savedResult);
    } catch (error) {
      setSaveStatus('error');
      console.error('Save failed:', error);
    }
  }, [currentWorkflow.name, currentWorkflowId, currentDescription]);

  const handleDeleteWorkflow = async (id: string) => {
    await toast.promise(
      workflowService.deleteWorkflow(id),
      {
        loading: 'Deleting workflow...',
        success: <b>Workflow deleted.</b>,
        error: <b>Could not delete workflow.</b>,
      }
    );
    // Refresh the workflow list
    const updatedWorkflows = await workflowService.getWorkflows();
    setWorkflows(updatedWorkflows);
    // If the deleted workflow was active, navigate away
    if (currentWorkflowId === id) {
      if (updatedWorkflows.length > 0) {
        setCurrentWorkflowId(updatedWorkflows[0].id);
        const full = await workflowService.getWorkflow(updatedWorkflows[0].id);
        if (full && (window as any).loadCanvasWorkflowData) {
          (window as any).loadCanvasWorkflowData(full.definition);
        }
      } else {
        onNewWorkflow();
      }
    }
  };

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
        onDeleteWorkflow={handleDeleteWorkflow}
        isCollapsed={isLeftSidebarCollapsed}
        onToggleCollapse={() => setIsLeftSidebarCollapsed(!isLeftSidebarCollapsed)}
      />

      <div className="flex-1 flex flex-col min-w-0 relative">
        {/* Topbar with Editable Title */}
        <Topbar
          workflowName={currentWorkflow.name}
          workflowDescription={currentDescription}
          onRename={(newName) => onRenameWorkflow(currentWorkflow.id, newName)}
          onDescribeWorkflow={(desc) => setCurrentDescription(desc)}
          onToggleNodePalette={() => setIsRightSidebarOpen(!isRightSidebarOpen)}
          isNodePaletteOpen={isRightSidebarOpen}
          onNewWorkflow={onNewWorkflow}
          onSave={handleSave}
          saveStatus={saveStatus}
        />

        <div className="flex-1 flex overflow-hidden">
          {/* Main Canvas Area */}
          <main className="flex-1 overflow-hidden relative">
            <WorkflowCanvas key={currentWorkflowId} workflowId={currentWorkflowId} />
          </main>

          {/* Node Palette (Right Sidebar) - Now a push-sidebar */}
          <div
            className={`h-full border-l border-slate-200 bg-white transition-all duration-300 ease-in-out overflow-hidden flex-shrink-0 ${isRightSidebarOpen ? 'w-[320px] opacity-100' : 'w-0 opacity-0 border-none'
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
