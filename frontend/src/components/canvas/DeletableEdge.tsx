import React from 'react';
import {
  EdgeProps,
  getBezierPath,
  EdgeLabelRenderer,
  BaseEdge,
  useReactFlow,
} from 'reactflow';

const DeletableEdge: React.FC<EdgeProps> = ({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style,
  markerEnd,
  data,
}) => {
  const { deleteElements } = useReactFlow();

  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    deleteElements({ edges: [{ id }] });
  };

  // Apply path-aware styling
  const isActive = data?.isActivePath;
  const executionState = data?.executionState as 'idle' | 'running' | 'success' | 'failed' | undefined;
  const isFailedPath = executionState === 'failed';
  const isRunningPath = executionState === 'running';
  const edgeStyle = {
    ...style,
    stroke: isFailedPath ? '#f43f5e' : isActive ? '#10b981' : (style?.stroke || '#94a3b8'),
    strokeWidth: (isActive || isFailedPath) ? 4 : (style?.strokeWidth || 2),
    opacity: (isActive || isFailedPath) ? 1 : 0.6,
    filter: isRunningPath ? 'drop-shadow(0 0 6px rgba(16,185,129,0.45))' : undefined,
  };

  // Prepare markerEnd based on its type (string or object)
  const markerEndConfig = typeof markerEnd === 'object' && markerEnd !== null
    ? {
      ...(markerEnd as any),
      color: isFailedPath ? '#f43f5e' : isActive ? '#10b981' : ((markerEnd as any).color || '#94a3b8'),
    }
    : markerEnd;

  return (
    <>
      <BaseEdge
        path={edgePath}
        markerEnd={markerEndConfig}
        style={edgeStyle}
        interactionWidth={20}
      />

      <EdgeLabelRenderer>
        <div
          style={{
            position: 'absolute',
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            pointerEvents: 'all',
          }}
          className="nodrag nopan group/edge"
        >
          {/* Delete button — visible on edge hover */}
          <button
            id={`delete-edge-${id}`}
            onClick={handleDelete}
            title="Remove connection"
            className="w-5 h-5 rounded-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-300 dark:text-slate-600 hover:text-red-500 dark:hover:text-red-400 hover:border-red-300 dark:hover:border-red-900 hover:bg-red-50 dark:hover:bg-red-900/20 transition-all flex items-center justify-center shadow-sm opacity-0 group-hover/edge:opacity-100"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="9"
              height="9"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="3"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M18 6 6 18" />
              <path d="m6 6 12 12" />
            </svg>
          </button>
        </div>
      </EdgeLabelRenderer>
    </>
  );
};

export default DeletableEdge;
