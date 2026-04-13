import React, { useState, useCallback, useEffect, useRef } from 'react';
import toast from 'react-hot-toast';
import Topbar from './Topbar';
import ExecutionLogsFooter from './ExecutionLogsFooter';
import NodeSidebar from '../sidebar/NodeSidebar';
import WorkflowSidebar from '../sidebar/WorkflowSidebar';
import WorkflowCanvas from '../canvas/WorkflowCanvas';
import { workflowService } from '../../services/workflowService';
import { ExecutionDetail } from '../../services/executionService';
import AIWorkflowChatPanel from '../chat/AIWorkflowChatPanel';
import { aiService, Message } from '../../services/aiService';

interface Workflow {
  id: string;
  name: string;
  description?: string;
  is_published?: boolean;
}

const MainLayout: React.FC = () => {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [currentWorkflowId, setCurrentWorkflowId] = useState<string>('');
  const [newWorkflowDraftName, setNewWorkflowDraftName] = useState<string>('Untitled Workflow');
  const [isLoading, setIsLoading] = useState(true);
  const [isLeftSidebarCollapsed, setIsLeftSidebarCollapsed] = useState(false);
  const [isAiAssistantOpen, setIsAiAssistantOpen] = useState(false);
  const [isRightSidebarOpen, setIsRightSidebarOpen] = useState(false);

  // AI Chat & Resize State
  const [chatMessages, setChatMessages] = useState<Message[]>([]);
  const [isAiLoading, setIsAiLoading] = useState(false);
  const [chatPanelWidth, setChatPanelWidth] = useState(400);
  const chatResizingRef = useRef(false);
  const chatStartXRef = useRef(0);
  const chatStartWidthRef = useRef(400);

  // Save Status State
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [currentDescription, setCurrentDescription] = useState<string>('');

  // Logs Panel State
  const [logsExpanded, setLogsExpanded] = useState(false);
  const [logsPanelHeight, setLogsPanelHeight] = useState(320);
  const [currentExecutionId, setCurrentExecutionId] = useState<string | null>(null);
  const [currentExecutionDetail, setCurrentExecutionDetail] = useState<ExecutionDetail | null>(null);
  const logsResizingRef = useRef(false);
  const logsStartYRef = useRef(0);
  const logsStartHeightRef = useRef(320);
  const FOOTER_COLLAPSED_HEIGHT = 52;

  // Resize log panel
  useEffect(() => {
    const handleMouseMove = (event: MouseEvent) => {
      if (!logsResizingRef.current) return;
      const delta = logsStartYRef.current - event.clientY;
      const nextHeight = Math.min(560, Math.max(220, logsStartHeightRef.current + delta));
      setLogsPanelHeight(nextHeight);
    };

    const handleMouseUp = () => {
      if (!logsResizingRef.current) return;
      logsResizingRef.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
    };
  }, []);

  // AI Chat Resizing logic
  useEffect(() => {
    const handleMouseMove = (event: MouseEvent) => {
      if (!chatResizingRef.current) return;
      const delta = event.clientX - chatStartXRef.current;
      const nextWidth = Math.min(700, Math.max(300, chatStartWidthRef.current + delta));
      setChatPanelWidth(nextWidth);
    };

    const handleMouseUp = () => {
      if (!chatResizingRef.current) return;
      chatResizingRef.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
    };
  }, []);

  const handleLogResizeStart = useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    logsResizingRef.current = true;
    logsStartYRef.current = event.clientY;
    logsStartHeightRef.current = logsPanelHeight;
    document.body.style.cursor = 'row-resize';
    document.body.style.userSelect = 'none';
  }, [logsPanelHeight]);

  const handleChatResizeStart = useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    chatResizingRef.current = true;
    chatStartXRef.current = event.clientX;
    chatStartWidthRef.current = chatPanelWidth;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, [chatPanelWidth]);

  // Execution State
  const [executionState, setExecutionState] = useState<string>('idle');
  const [lastExecutionDuration, setLastExecutionDuration] = useState<number | undefined>(undefined);

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

  useEffect(() => {
    (window as any).openNodePalette = () => setIsRightSidebarOpen(true);
    return () => {
      delete (window as any).openNodePalette;
    };
  }, []);

  const currentWorkflow = currentWorkflowId === 'new'
    ? { id: 'new', name: newWorkflowDraftName, is_published: false }
    : workflows.find(w => w.id === currentWorkflowId) || workflows[0] || { id: 'new', name: 'Untitled Workflow', is_published: false };

  const isPublished = currentWorkflow.is_published || false;
  const footerOffset = logsExpanded ? logsPanelHeight : FOOTER_COLLAPSED_HEIGHT;

  const onNewWorkflow = useCallback(() => {
    // They will get an ID once saved to the backend.
    setCurrentWorkflowId('new');
    setNewWorkflowDraftName('Untitled Workflow');
    setCurrentDescription('');
    if ((window as any).loadCanvasWorkflowData) {
      (window as any).loadCanvasWorkflowData({ nodes: [], edges: [] });
    }
    setCurrentExecutionId(null);
    setCurrentExecutionDetail(null);
    setExecutionState('idle');
    setLastExecutionDuration(undefined);
    toast.success('Started a fresh workflow draft');
  }, []);

  const onRenameWorkflow = useCallback((id: string, newName: string) => {
    if (id === 'new') {
      setNewWorkflowDraftName(newName);
    } else {
      setWorkflows(prev => prev.map(w => w.id === id ? { ...w, name: newName } : w));
    }
    toast.success(`Workflow renamed to "${newName}"`);
  }, []);

  const handleImportWorkflow = useCallback((data: any) => {
    if (!data || !data.definition) {
      toast.error('Invalid workflow file');
      return;
    }

    // Update current workflow in list or create a "new" draft if current is 'new'
    if (currentWorkflowId === 'new') {
      setNewWorkflowDraftName(data.name || 'Imported Workflow');
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
    setCurrentExecutionId(null);
    setCurrentExecutionDetail(null);
    setExecutionState('idle');
    setLastExecutionDuration(undefined);
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

  const handleSendMessage = useCallback(async (content: string) => {
    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content,
      timestamp: new Date().toISOString(),
    };

    setChatMessages(prev => [...prev, userMsg]);
    setIsAiLoading(true);

    try {
      // Get current workflow state to provide context to the AI
      const currentWorkflowData = (window as any).getCanvasWorkflowData?.(currentWorkflow.name);
      const workflowContext = currentWorkflowData?.definition;

      const response = await aiService.generateWorkflow(content, workflowContext);
      const assistantMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: response.message,
        timestamp: new Date().toISOString(),
        ...(response.workflow ? { workflow: response.workflow } : {})
      } as any;
      setChatMessages(prev => [...prev, assistantMsg]);
    } catch (error) {
      toast.error('AI Architect is currently unavailable');
    } finally {
      setIsAiLoading(false);
    }
  }, []);

  const handleApplyAiWorkflow = useCallback((workflow: any) => {
    const isDirty = (window as any).isCanvasDirty?.();

    if (isDirty) {
      if (!window.confirm('You have unsaved changes. Applying this AI-generated workflow will replace your current work. Continue?')) {
        return;
      }
    }

    if ((window as any).applyAiWorkflow) {
      (window as any).applyAiWorkflow(workflow);
      toast.success('AI Workflow applied! Review and save your changes.');
    }
  }, []);

  return (
    <div className="flex h-screen overflow-hidden bg-white dark:bg-slate-950 font-sans antialiased text-slate-900 dark:text-slate-100 transition-colors duration-300">
      {isLoading && (
        <div className="absolute inset-0 z-[9999] bg-white dark:bg-slate-900 flex items-center justify-center">
          <div className="flex flex-col items-center gap-4">
            <div className="w-10 h-10 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" />
            <p className="text-sm font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest">Loading...</p>
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
          executionState={executionState}
          lastExecutionTime={lastExecutionDuration}
        />

        <div className="flex-1 flex overflow-hidden relative">
          {/* Main Canvas Area */}
          <main className="flex-1 overflow-hidden relative">
            <WorkflowCanvas
              key={currentWorkflowId}
              workflowId={currentWorkflowId}
              footerOffset={footerOffset}
              onToggleAiAssistant={() => setIsAiAssistantOpen(!isAiAssistantOpen)}
              isAiAssistantOpen={isAiAssistantOpen}
              onExecutionStart={(executionId) => {
                setCurrentExecutionId(executionId);
                setCurrentExecutionDetail(null);
                setExecutionState('RUNNING');
                setLastExecutionDuration(undefined);
              }}
              onExecutionUpdate={(detail) => {
                setCurrentExecutionDetail(detail);
                setExecutionState(
                  detail.status === 'PENDING' ? 'RUNNING' : detail.status
                );

                if (detail.started_at && detail.finished_at) {
                  setLastExecutionDuration(
                    new Date(detail.finished_at).getTime() - new Date(detail.started_at).getTime()
                  );
                } else if (detail.status === 'RUNNING' || detail.status === 'PENDING') {
                  setLastExecutionDuration(undefined);
                }
              }}
            />
          </main>

          <ExecutionLogsFooter
            executionId={currentExecutionId}
            executionDetail={currentExecutionDetail}
            isExpanded={logsExpanded}
            panelHeight={logsPanelHeight}
            onToggle={() => setLogsExpanded((prev) => !prev)}
            onResizeStart={handleLogResizeStart}
          />

          <AIWorkflowChatPanel
            isOpen={isAiAssistantOpen}
            onClose={() => setIsAiAssistantOpen(false)}
            messages={chatMessages}
            onSendMessage={handleSendMessage}
            onApplyWorkflow={handleApplyAiWorkflow}
            isLoading={isAiLoading}
            width={chatPanelWidth}
            onResizeStart={handleChatResizeStart}
            style={{ paddingBottom: `${footerOffset}px` }}
          />
        </div>
      </div>

      {/* Node Sidebar (Right) - Now a top-level sibling */}
      <div
        className={`h-screen border-l border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 transition-all duration-300 ease-in-out overflow-hidden flex-shrink-0 z-[40] ${
          isRightSidebarOpen ? 'w-80 opacity-100' : 'w-0 opacity-0 border-none'
        }`}
      >
        <div className="w-80 h-full overflow-hidden">
          <NodeSidebar 
            onClose={() => setIsRightSidebarOpen(false)} 
            onSelect={(type) => {
              if ((window as any).addNodeAtCenter) {
                (window as any).addNodeAtCenter(type);
              }
            }}
          />
        </div>
      </div>
    </div>
  );
};

export default MainLayout;
