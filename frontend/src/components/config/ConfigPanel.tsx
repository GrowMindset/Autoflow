import React, { useState } from 'react';
import { createPortal } from 'react-dom';
import { WorkflowNode } from '../../types/workflow';
import JsonTree from './JsonTree';
import ConfigForm from './ConfigForm';

interface ConfigPanelProps {
  node: WorkflowNode;
  upstreamData: any;
  onClose: () => void;
  onUpdate: (id: string, config: Record<string, any>, output?: any) => void;
}

const ConfigPanel: React.FC<ConfigPanelProps> = ({ node, upstreamData, onClose, onUpdate }) => {
  const [output, setOutput] = useState<any>(node.data.last_output || null);
  const [isExecuting, setIsExecuting] = useState(false);
  const [isLeftVisible, setIsLeftVisible] = useState(true);
  const [isRightVisible, setIsRightVisible] = useState(true);

  // Sync state if node changes externally
  const handleConfigChange = (key: string, value: any) => {
    const nextConfig = { ...node.data.config, [key]: value };
    onUpdate(node.id, nextConfig);
  };

  const handleExecute = () => {
    setIsExecuting(true);
    // Simulate node execution
    setTimeout(() => {
      const mockResult = {
        status: "success",
        timestamp: new Date().toISOString(),
        node_id: node.id,
        summary: `Processed ${Object.keys(node.data.config).length} config parameters`,
        data: { ...node.data.config }
      };
      setOutput(mockResult);
      onUpdate(node.id, node.data.config, mockResult);
      setIsExecuting(false);
    }, 1000);
  };

  return createPortal(
    <div className="fixed inset-0 z-[9999] bg-slate-900/60 backdrop-blur-md flex items-center justify-center p-4 md:p-8 animate-in fade-in zoom-in-95 duration-300">
      <div className="bg-white w-full h-[92vh] max-w-[1700px] rounded-[2.5rem] shadow-[0_40px_100px_rgba(0,0,0,0.5)] flex flex-col overflow-hidden border border-white/20">

        {/* Header */}
        <div className="h-20 px-8 border-b border-slate-100 flex items-center justify-between bg-white z-20">
          <div className="flex items-center gap-5">
            <div className="p-3 rounded-2xl bg-slate-50 border border-slate-100 shadow-sm">
              <div className={`w-4 h-4 rounded-full ${node.data.category === 'trigger' ? 'bg-emerald-500' :
                node.data.category === 'action' ? 'bg-blue-500' :
                  node.data.category === 'transform' ? 'bg-amber-500' : 'bg-purple-500'
                } shadow-[0_0_10px_rgba(0,0,0,0.1)]`} />
            </div>
            <div>
              <h2 className="text-base font-black text-slate-800 tracking-tight">{node.data.label}</h2>
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest bg-slate-100 px-2 py-0.5 rounded-full">{node.data.type}</span>
                <span className="text-[10px] text-slate-300 font-mono">ID: {node.id.split('_').slice(0, 2).join('_')}</span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <button
              onClick={handleExecute}
              disabled={isExecuting}
              className={`flex items-center gap-2.5 px-6 py-2.5 bg-slate-900 text-white rounded-2xl text-xs font-bold hover:bg-slate-800 transition-all shadow-[0_10px_20px_rgba(0,0,0,0.15)] active:scale-95 disabled:opacity-50 ${isExecuting ? 'animate-pulse' : ''}`}
            >
              {isExecuting ? 'Executing...' : (
                <>
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="m5 3 14 9-14 9V3z" /></svg>
                  Execute Node
                </>
              )}
            </button>
            <div className="w-px h-8 bg-slate-100 mx-2" />
            <button
              onClick={onClose}
              className="p-3 hover:bg-slate-100 rounded-2xl transition-all text-slate-400 hover:text-slate-800 active:bg-slate-200"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18" /><path d="m6 6 12 12" /></svg>
            </button>
          </div>
        </div>

        {/* 3-Column Layout */}
        <div className="flex-1 flex overflow-hidden relative bg-slate-50/20">

          {/* Column 1: Input Data */}
          <div className={`flex flex-col border-r border-slate-100 transition-all duration-500 ease-in-out bg-white ${isLeftVisible ? 'w-[350px] opacity-100' : 'w-12 opacity-80'}`}>
            <div className="h-12 px-4 flex items-center justify-between border-b border-slate-50 bg-white group select-none">
              {isLeftVisible ? (
                <>
                  <span className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">INPUT DATA</span>
                  <button onClick={() => setIsLeftVisible(false)} className="p-1 hover:bg-slate-100 rounded-md text-slate-300 hover:text-slate-600 transition-colors">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m15 18-6-6 6-6" /></svg>
                  </button>
                </>
              ) : (
                <button onClick={() => setIsLeftVisible(true)} className="w-full h-full flex items-center justify-center hover:bg-slate-50 text-slate-300 hover:text-blue-500 transition-all">
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="m9 18 6-6-6-6" /></svg>
                </button>
              )}
            </div>
            {isLeftVisible && (
              <div className="flex-1 overflow-auto custom-scrollbar p-2 animate-in slide-in-from-left-4 duration-300">
                {upstreamData ? (
                  <JsonTree data={upstreamData} />
                ) : (
                  <div className="h-full flex flex-col items-center justify-center text-slate-300 p-8 text-center space-y-4">
                    <div className="p-4 rounded-full bg-slate-50 border border-slate-100">
                      <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect width="8" height="4" x="8" y="2" rx="1" ry="1" /><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" /><path d="M12 11h4" /><path d="M12 16h4" /><path d="M8 11h.01" /><path d="M8 16h.01" /></svg>
                    </div>
                    <p className="text-xs font-medium leading-relaxed">No input data available. <br />Connect an upstream node.</p>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Column 2: Parameters Form */}
          <div className="flex-1 flex flex-col overflow-hidden bg-white z-10 shadow-[0_0_50px_rgba(0,0,0,0.02)]">
            <div className="h-12 px-8 flex items-center border-b border-slate-50 bg-white">
              <span className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">PARAMETERS</span>
            </div>
            <div className="flex-1 overflow-auto p-10 custom-scrollbar">
              <div className="max-w-2xl mx-auto pb-20">
                <ConfigForm
                  nodeType={node.data.type}
                  config={node.data.config}
                  onChange={handleConfigChange}
                />
              </div>
            </div>
          </div>

          {/* Column 3: Output Data */}
          <div className={`flex flex-col border-l border-slate-100 transition-all duration-500 ease-in-out bg-white ${isRightVisible ? 'w-[400px] opacity-100' : 'w-12 opacity-80'}`}>
            <div className="h-12 px-4 flex items-center justify-between border-b border-slate-50 bg-white group select-none">
              {!isRightVisible ? (
                <button onClick={() => setIsRightVisible(true)} className="w-full h-full flex items-center justify-center hover:bg-slate-50 text-slate-300 hover:text-blue-500 transition-all">
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="m15 18-6-6 6-6" /></svg>
                </button>
              ) : (
                <>
                  <button onClick={() => setIsRightVisible(false)} className="p-1 hover:bg-slate-100 rounded-md text-slate-300 hover:text-slate-600 transition-colors">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m9 18 6-6-6-6" /></svg>
                  </button>
                  <span className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">OUTPUT DATA</span>
                </>
              )}
            </div>
            {isRightVisible && (
              <div className="flex-1 overflow-auto custom-scrollbar p-2 animate-in slide-in-from-right-4 duration-300">
                {output ? (
                  <JsonTree data={output} />
                ) : (
                  <div className="h-full flex flex-col items-center justify-center text-slate-300 p-8 text-center space-y-4">
                    <div className="p-4 rounded-full bg-slate-50 border border-slate-100">
                      <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12a9 9 0 1 1-6.219-8.56" /><path d="M22 10 16 4" /><path d="m22 4-6 6" /></svg>
                    </div>
                    <p className="text-xs font-medium leading-relaxed">No output data yet. <br />Click 'Execute Node' to see results.</p>
                  </div>
                )}
              </div>
            )}
          </div>

        </div>
      </div>
    </div>,
    document.body
  );
};

export default ConfigPanel;
