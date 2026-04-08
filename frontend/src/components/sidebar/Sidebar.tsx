function Sidebar() {
  return (
    <aside className="w-72 border-r border-slate-200 bg-white p-6">
      <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-slate-500">Node Palette</h2>
      <ul className="space-y-2 text-sm text-slate-700">
        <li className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2">Trigger Nodes</li>
        <li className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2">Action Nodes</li>
        <li className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2">Transform Nodes</li>
      </ul>
    </aside>
  );
}

export default Sidebar;
