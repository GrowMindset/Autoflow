import React from 'react';
import { NODE_LIBRARY } from '../../constants/nodeLibrary';
import CategorySection from './CategorySection';

const NodeSidebar: React.FC = () => {
  return (
    <aside className="w-80 bg-white dark:bg-slate-900 overflow-y-auto h-full p-5 flex flex-col gap-6 transition-colors duration-300">
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />
          <h2 className="text-sm font-bold uppercase tracking-widest text-slate-400 dark:text-slate-500">Node Palette</h2>
        </div>
      </div>

      <div className="flex flex-col gap-6">
        <CategorySection
          title="Triggers"
          category="trigger"
          nodes={NODE_LIBRARY.trigger}
          isOpenDefault
        />
        <CategorySection
          title="Actions"
          category="action"
          nodes={NODE_LIBRARY.action}
          isOpenDefault
        />
        <CategorySection
          title="Data Transform"
          category="transform"
          nodes={NODE_LIBRARY.transform}
        />
        <CategorySection
          title="AI"
          category="ai"
          nodes={NODE_LIBRARY.ai}
        />
      </div>
    </aside>
  );
};

export default NodeSidebar;
