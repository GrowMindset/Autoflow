import React, { useState, useCallback, useEffect } from 'react';
import toast from 'react-hot-toast';
import Topbar from './Topbar';
import NodeSidebar from '../sidebar/NodeSidebar';
import WorkflowSidebar from '../sidebar/WorkflowSidebar';
import WorkflowCanvas from '../canvas/WorkflowCanvas';
import { workflowService } from '../../services/workflowService';
import { executionService } from '../../services/executionService';

interface Workflow {
  id: string;
  name: string;
  description?: string;
  is_published?: boolean;
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

  // Logs Panel State
  const [logsVisible, setLogsVisible] = useState(false);
  const [executionLogs, setExecutionLogs] = useState<any[]>([]);

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

  const currentWorkflow = workflows.find(w => w.id === currentWorkflowId) || workflows[0] || { id: 'new', name: 'Untitled Workflow', is_published: false };
  const isPublished = currentWorkflow.is_published || false;

  const loadExecutionLogs = useCallback(async () => {
    if (currentWorkflowId === 'new') {
      toast.error('Please save the workflow first');
      return;
    }
    try {
      const executionDetail = await executionService.getLatestExecution(currentWorkflowId);
      const logs = executionDetail.node_results.map((node: any) => ({
        node_id: node.node_id,
        node_type: node.node_type,
        status: node.status,
        error_message: node.error_message,
        started_at: node.started_at,
        finished_at: node.finished_at,
        branch: node.output_data?._branch ?? node.input_data?._branch ?? null,
      }));
      setExecutionLogs(logs);
    } catch (error) {
      console.error('Failed to load execution logs', error);
      toast.error('Failed to load execution logs');
    }
  }, [currentWorkflowId]);

  const onNewWorkflow = useCallback(() => {
    // They will get an ID once saved to the backend.
    setCurrentWorkflowId('new');
    setCurrentDescription('');
    if ((window as any).loadCanvasWorkflowData) {
      (window as any).loadCanvasWorkflowData({ nodes: [], edges: [] });
    }
    toast.success('Started a fresh workflow draft');
  }, []);

  const onRenameWorkflow = useCallback((id: string, newName: string) => {
    setWorkflows(prev => prev.map(w => w.id === id ? { ...w, name: newName } : w));
    toast.success(`Workflow renamed to "${newName}"`);
  }, []);

  const handleImportWorkflow = useCallback((data: any) => {
    if (!data || !data.definition) {
      toast.error('Invalid workflow file');
      return;
    }

    // Update current workflow in list or create a "new" draft if current is 'new'
    if (currentWorkflowId === 'new') {
      // Just update the temporary visual state
      setWorkflows(prev => prev.map(w => w.id === 'new' ? { ...w, name: data.name || 'Imported Workflow' } : w));
    } else {
      setWorkflows(prev => prev.map(w => w.id === currentWorkflowId ? { ...w, name: data.name || w.name } : w));
    }

    setCurrentDescription(data.definition.description || '');
    
    // Load into canvas
    if ((window as any).loadCanvasWorkflowData) {
      (window as any).loadCanvasWorkflowData(data.definition);
    }
    
    toast.success('Workflow data loaded. Click "Save Changes" to persist.');
  }, [currentWorkflowId, setWorkflows]);

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

  const handleTogglePublish = useCallback(async () => {
    if (currentWorkflowId === 'new') {
      toast.error('Please save the workflow first');
      return;
    }

    const newStatus = !isPublished;
    try {
      await toast.promise(
        workflowService.updatePublishStatus(currentWorkflowId, newStatus),
        {
          loading: newStatus ? 'Publishing...' : 'Unpublishing...',
          success: <b>Workflow {newStatus ? 'published' : 'unpublished'} successfully!</b>,
          error: <b>Failed to update publish status.</b>,
        }
      );

      // Update local state
      setWorkflows(prev => prev.map(w =>
        w.id === currentWorkflowId ? { ...w, is_published: newStatus } : w
      ));
    } catch (error) {
      console.error('Failed to toggle publish status:', error);
    }
  }, [currentWorkflowId, isPublished]);

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
          onDescribeWorkflow={(desc) => {
            setCurrentDescription(desc);
            toast.success('Description updated');
          }}
          onToggleNodePalette={() => setIsRightSidebarOpen(!isRightSidebarOpen)}
          isNodePaletteOpen={isRightSidebarOpen}
          onSave={handleSave}
          isPublished={isPublished}
          onTogglePublish={handleTogglePublish}
          saveStatus={saveStatus}
          onImport={handleImportWorkflow}
          onToggleLogs={() => {
            setLogsVisible(!logsVisible);
            if (!logsVisible) loadExecutionLogs();
          }}
          logsVisible={logsVisible}
        />

        <div className="flex-1 flex overflow-hidden">
          {/* Main Canvas Area */}
          <main className="flex-1 overflow-hidden relative">
            <WorkflowCanvas key={currentWorkflowId} workflowId={currentWorkflowId} />

            {/* Logs Panel */}
            {logsVisible && (
              <div className="absolute bottom-0 left-0 right-0 bg-white border-t border-slate-200 p-4 max-h-64 overflow-y-auto shadow-lg">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-bold text-slate-800">Execution Logs</h3>
                  <button
                    onClick={() => setLogsVisible(false)}
                    className="text-slate-400 hover:text-slate-600"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="18" y1="6" x2="6" y2="18"/>
                      <line x1="6" y1="6" x2="18" y2="18"/>
                    </svg>
                  </button>
                </div>
                {executionLogs.length === 0 ? (
                  <p className="text-sm text-slate-500">No execution logs available. Run the workflow to see logs.</p>
                ) : (
                  <div className="space-y-2">
                    {executionLogs.map((log, index) => (
                      <div key={index} className="flex items-start gap-3 p-2 bg-slate-50 rounded text-xs">
                        <div className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${log.status === 'SUCCEEDED' ? 'bg-green-500' : log.status === 'FAILED' ? 'bg-red-500' : 'bg-yellow-500'}`} />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="font-mono text-slate-600 truncate">{log.node_id}</span>
                            <span className="text-slate-400">({log.node_type})</span>
                            <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-widest ${log.status === 'SUCCEEDED' ? 'bg-green-100 text-green-700' : log.status === 'FAILED' ? 'bg-red-100 text-red-700' : 'bg-yellow-100 text-yellow-700'}`}>
                              {log.status}
                            </span>
                          </div>
                          {log.error_message && (
                            <div className="text-red-600 bg-red-50 p-2 rounded text-[11px] mt-1">
                              {log.error_message}
                            </div>
                          )}
                          {log.branch && (
                            <div className="text-slate-600 text-[11px] mt-1">
                              Branch: <span className="font-semibold">{log.branch}</span>
                            </div>
                          )}
                          {log.started_at && log.finished_at && (
                            <div className="text-slate-400 text-[10px] mt-1">
                              {new Date(log.started_at).toLocaleTimeString()} - {new Date(log.finished_at).toLocaleTimeString()}
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
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
