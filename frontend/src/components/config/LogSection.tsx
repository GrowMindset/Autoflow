import React from 'react';
import JsonTree from './JsonTree';

interface LogSectionProps {
  title: string;
  data: any;
  icon?: React.ReactNode;
}

const LogSection: React.FC<LogSectionProps> = ({ title, data, icon }) => (
  <div className="flex flex-col gap-2">
    <div className="flex items-center gap-2 px-1">
      {icon}
      <span className="text-[10px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500">{title}</span>
    </div>
    <div className="rounded-2xl border border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/20 p-2 shadow-sm transition-colors">
      {data ? (
        <JsonTree data={data} />
      ) : (
        <span className="text-[10px] text-slate-300 dark:text-slate-600 italic px-2 py-4 block">No data recorded</span>
      )}
    </div>
  </div>
);

export default LogSection;
