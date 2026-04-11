import React, { useState } from 'react';
import { NodeDefinition } from '../../constants/nodeLibrary';
import NodeItem from './NodeItem';

interface CategorySectionProps {
  title: string;
  category: string;
  nodes: NodeDefinition[];
  isOpenDefault?: boolean;
}

const CategorySection: React.FC<CategorySectionProps> = ({ title, category, nodes, isOpenDefault = false }) => {
  const [isOpen, setIsOpen] = useState(isOpenDefault);
  const [isExpanded, setIsExpanded] = useState(false);

  const getCategoryColor = (cat: string) => {
    switch (cat) {
      case 'trigger': return 'bg-emerald-500';
      case 'action': return 'bg-blue-500';
      case 'transform': return 'bg-amber-500';
      case 'ai': return 'bg-purple-500';
      default: return 'bg-slate-300';
    }
  };

  const displayedNodes = isExpanded ? nodes : nodes.slice(0, 4);
  const hasMore = nodes.length > 4;

  return (
    <div className="flex flex-col gap-1">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center justify-between p-2 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-800 transition-all group"
      >
        <div className="flex items-center gap-3">
            <div className={`w-1.5 h-1.5 rounded-full ${getCategoryColor(category)}`} />
            <span className="text-[10px] font-bold uppercase tracking-widest text-slate-500 dark:text-slate-300">{title}</span>
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
          className={`text-slate-300 dark:text-slate-700 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`}
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>

      {isOpen && (
        <div className="flex flex-col gap-1.5 pl-4 py-1 animate-in slide-in-from-top-1 duration-200">
          {displayedNodes.map((node) => (
            <NodeItem key={node.type} node={node} />
          ))}
          
          {hasMore && (
            <button 
              onClick={(e) => {
                e.stopPropagation();
                setIsExpanded(!isExpanded);
              }}
              className="text-[9px] font-bold text-slate-400 hover:text-blue-500 transition-colors uppercase tracking-widest px-2 py-1 flex items-center gap-1 group"
            >
              {isExpanded ? (
                <>Show Less <svg xmlns="http://www.w3.org/2000/svg" width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="m18 15-6-6-6 6"/></svg></>
              ) : (
                <>+{nodes.length - 4} more <svg xmlns="http://www.w3.org/2000/svg" width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="m6 9 6 6 6-6"/></svg></>
              )}
            </button>
          )}
        </div>
      )}
    </div>
  );
};

export default CategorySection;
