import React from 'react';

interface NodeBadgeProps {
  children: React.ReactNode;
  variant?: 'trigger' | 'action' | 'transform' | 'ai' | 'neutral';
}

const NodeBadge: React.FC<NodeBadgeProps> = ({ children, variant = 'neutral' }) => {
  const styles = {
    trigger: 'bg-emerald-100 text-emerald-700 border-emerald-200',
    action: 'bg-blue-100 text-blue-700 border-blue-200',
    transform: 'bg-amber-100 text-amber-700 border-amber-200',
    ai: 'bg-purple-100 text-purple-700 border-purple-200',
    neutral: 'bg-slate-100 text-slate-600 border-slate-200',
  };

  return (
    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider border ${styles[variant]}`}>
      {children}
    </span>
  );
};

export default NodeBadge;
