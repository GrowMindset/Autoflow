import React from 'react';
import { NodeDefinition } from '../../constants/nodeLibrary';
import NodeBadge from './NodeBadge';

interface NodeItemProps {
  node: NodeDefinition;
}

const NodeItem: React.FC<NodeItemProps> = ({ node }) => {
  const onDragStart = (event: React.DragEvent) => {
    event.dataTransfer.setData('application/reactflow', node.type);
    event.dataTransfer.effectAllowed = 'move';
  };

  return (
    <div
      className={`p-2 rounded-lg border border-slate-100 bg-white hover:border-blue-200 transition-all cursor-grab active:cursor-grabbing group ${
        node.is_dummy ? 'opacity-60 grayscale-[0.2]' : ''
      }`}
      draggable
      onDragStart={onDragStart}
    >
      <div className="flex flex-col gap-1">
        <div className="flex items-center justify-between gap-2 overflow-hidden">
          <h4 className="text-[11px] font-bold text-slate-800 tracking-tight truncate">{node.label}</h4>
          {node.is_dummy && <NodeBadge variant="neutral">Soon</NodeBadge>}
        </div>
        <p className="text-[10px] text-slate-400 line-clamp-1">
          {node.description}
        </p>
      </div>
    </div>
  );
};

export default NodeItem;
