import Sidebar from '../sidebar/Sidebar';
import Topbar from './Topbar';
import WorkflowCanvas from '../canvas/WorkflowCanvas';

function Layout() {
  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden">
      <Topbar 
        workflowName="Legacy Layout" 
        workflowDescription="" 
        onRename={() => {}} 
        onDescribeWorkflow={() => {}} 
        onToggleNodePalette={() => {}} 
        isNodePaletteOpen={false} 
        onNewWorkflow={() => {}} 
        onSave={() => {}} 
        saveStatus="idle"
      />
      <div className="flex min-h-0 flex-1">
        <Sidebar />
        <main className="min-h-0 flex-1 bg-slate-50 p-4">
          <div className="h-full w-full overflow-hidden rounded-lg border border-slate-200 bg-white">
            <WorkflowCanvas />
          </div>
        </main>
      </div>
    </div>
  );
}

export default Layout;
