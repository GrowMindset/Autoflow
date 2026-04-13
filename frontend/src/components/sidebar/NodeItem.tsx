import React from 'react';
import { NodeDefinition } from '../../constants/nodeLibrary';
import NodeBadge from './NodeBadge';

interface NodeItemProps {
  node: NodeDefinition;
  onSelect?: (type: string) => void;
}

const NodeItem: React.FC<NodeItemProps> = ({ node, onSelect }) => {
  const onDragStart = (event: React.DragEvent) => {
    event.dataTransfer.setData('application/reactflow', node.type);
    event.dataTransfer.effectAllowed = 'move';
  };

  return (
    <div
      onClick={() => onSelect?.(node.type)}
      className={`p-2 rounded-lg border border-slate-100 dark:border-slate-800 bg-white dark:bg-slate-800/50 hover:border-blue-200 dark:hover:border-blue-500/50 transition-all cursor-pointer active:cursor-grabbing group ${
        node.is_dummy ? 'opacity-60 grayscale-[0.2]' : ''
      }`}
      draggable
      onDragStart={onDragStart}
    >
      <div className="flex flex-col gap-1">
        <div className="flex items-center justify-between gap-2 overflow-hidden">
          <h4 className="text-[11px] font-bold text-slate-800 dark:text-slate-200 tracking-tight truncate">{node.label}</h4>
          {node.is_dummy && <NodeBadge variant="neutral">Soon</NodeBadge>}
        </div>
        <p className="text-[10px] text-slate-400 dark:text-slate-500 line-clamp-1">
          {node.description}
        </p>
      </div>
    </div>
  );
};

export default NodeItem;
