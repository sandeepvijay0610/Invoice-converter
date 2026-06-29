import { Link, useNavigate } from 'react-router-dom';
import { RefreshCw, Trash2, FileSpreadsheet, Upload, CheckSquare, Square, Minus } from 'lucide-react';
import { useInvoices } from '../hooks/useInvoices';
import { StatusBadge } from '../components/ui/StatusBadge';
import { LoadingSpinner } from '../components/ui/LoadingSpinner';
import { invoiceApi } from '../api/invoices';
import * as XLSX from 'xlsx';
import { useState, useEffect, useCallback, useRef } from 'react';
import type { InvoiceStatus } from '../types/invoice';

const STATUS_OPTIONS = [
  { value: '', label: 'All' },
  { value: 'READY_FOR_SAP', label: 'Ready for SAP' },
  { value: 'SAP_EXPORTED', label: 'Exported' },
  { value: 'PROCESSING', label: 'Processing' },
  { value: 'REQUIRES_MANUAL_REVIEW', label: 'Needs Review' },
  { value: 'FAILED', label: 'Failed' },
  { value: 'RATE_LIMITED', label: 'Rate Limited' },
];

export default function DashboardPage() {
  const { invoices, loading, statusFilter, setStatusFilter, refresh } = useInvoices();

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleteTargets, setDeleteTargets] = useState<string[]>([]);
  const [isDeleting, setIsDeleting] = useState(false);
  const tableRef = useRef<HTMLDivElement>(null);

  const allSelected = invoices.length > 0 && selected.size === invoices.length;
  const someSelected = selected.size > 0 && !allSelected;

  const toggleOne = (id: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const toggleAll = useCallback(() => {
    setSelected(allSelected ? new Set() : new Set(invoices.map(i => i.id)));
  }, [allSelected, invoices]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;
      if ((e.ctrlKey || e.metaKey) && e.key === 'a') { e.preventDefault(); toggleAll(); return; }
      if ((e.key === 'Delete' || e.key === 'Backspace') && selected.size > 0) { e.preventDefault(); setDeleteTargets([...selected]); return; }
      if (e.key === 'Escape') { setSelected(new Set()); return; }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selected, toggleAll]);

  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      await Promise.all(deleteTargets.map(id => invoiceApi.delete(id)));
      setSelected(new Set());
      setDeleteTargets([]);
      refresh();
    } catch (err) {
      console.error('Delete failed:', err);
    } finally {
      setIsDeleting(false);
    }
  };

  const exportAllToExcel = async () => {
    const summary = await invoiceApi.list('');
    const details = await Promise.all(summary.items.map(inv => invoiceApi.getById(inv.id)));
    const rows = details.map(inv => {
      const p = inv.extractedPayload;
      return {
        'Invoice ID': inv.id, 'Status': inv.status,
        'Vendor': p?.header_data?.vendor_name || '',
        'Invoice Number': p?.header_data?.invoice_number || '',
        'Date': p?.header_data?.invoice_date || '',
        'Total': p?.financial_data?.total_invoice_amount || 0,
      };
    });
    const wb = XLSX.utils.book_new();
    const ws = XLSX.utils.json_to_sheet(rows);
    ws['!cols'] = Object.keys(rows[0] || {}).map(k => ({ wch: Math.max(k.length, 15) }));
    XLSX.utils.book_append_sheet(wb, ws, 'Invoices');
    XLSX.writeFile(wb, 'All_Invoices.xlsx');
  };

  // Simple stats — monochrome, no colors
  const stats = [
    { label: 'Total', value: invoices.length, filter: '' },
    { label: 'Ready for SAP', value: invoices.filter(i => i.status === 'READY_FOR_SAP').length, filter: 'READY_FOR_SAP' },
    { label: 'Processing', value: invoices.filter(i => i.status === 'PROCESSING' || i.status === 'PENDING').length, filter: 'PROCESSING' },
    { label: 'Exported', value: invoices.filter(i => i.status === 'SAP_EXPORTED').length, filter: 'SAP_EXPORTED' },
    { label: 'Failed', value: invoices.filter(i => i.status === 'FAILED' || i.status === 'RATE_LIMITED').length, filter: 'FAILED' },
  ];

  return (
    <div className="h-full flex flex-col">

      {/* Delete modal */}
      {deleteTargets.length > 0 && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={() => setDeleteTargets([])} />
          <div className="relative bg-white rounded-2xl shadow-2xl p-6 w-full max-w-sm">
            <h3 className="text-base font-semibold text-gray-900 mb-1">
              Delete {deleteTargets.length} invoice{deleteTargets.length > 1 ? 's' : ''}?
            </h3>
            <p className="text-sm text-gray-400 mb-6">This cannot be undone.</p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setDeleteTargets([])} className="px-4 py-2 text-sm font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors">
                Cancel
              </button>
              <button onClick={handleDelete} disabled={isDeleting} className="px-4 py-2 text-sm font-medium text-white bg-red-500 hover:bg-red-600 rounded-lg transition-colors disabled:opacity-50">
                {isDeleting ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Invoices</h1>
          <p className="text-sm text-gray-400 mt-0.5">Manage your invoices and their statuses</p>
        </div>
        <div className="flex items-center gap-2">
          {selected.size > 0 && (
            <button
              onClick={() => setDeleteTargets([...selected])}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-red-50 text-red-600 border border-red-100 rounded-lg hover:bg-red-100 transition-colors text-sm font-medium"
            >
              <Trash2 className="w-3.5 h-3.5" />
              Delete {selected.size}
            </button>
          )}
          <button onClick={exportAllToExcel} className="inline-flex items-center gap-1.5 px-3 py-1.5 text-gray-600 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors text-sm font-medium">
            <FileSpreadsheet className="w-3.5 h-3.5" />
            Export
          </button>
          <Link to="/batch-upload" className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-gray-900 text-white rounded-lg hover:bg-gray-700 transition-colors text-sm font-medium">
            <Upload className="w-3.5 h-3.5" />
            Upload
          </Link>
          <select
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
            className="px-3 py-1.5 bg-white border border-gray-200 rounded-lg text-sm text-gray-600 focus:ring-2 focus:ring-gray-900 focus:border-gray-900 outline-none"
          >
            {STATUS_OPTIONS.map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
          </select>
          <button onClick={refresh} className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors" title="Refresh">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Stats — clean, monochrome */}
      <div className="grid grid-cols-5 gap-2 mb-5">
        {stats.map(s => (
          <button
            key={s.label}
            onClick={() => setStatusFilter(s.filter)}
            className={`text-left px-4 py-3 rounded-xl border transition-all ${
              statusFilter === s.filter
                ? 'bg-gray-900 border-gray-900 text-white'
                : 'bg-white border-gray-200 text-gray-700 hover:border-gray-300 hover:bg-gray-50'
            }`}
          >
            <p className="text-xl font-bold">{s.value}</p>
            <p className="text-xs opacity-60 mt-0.5">{s.label}</p>
          </button>
        ))}
      </div>

      {/* Table */}
      {loading ? (
        <LoadingSpinner message="Loading invoices…" />
      ) : invoices.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center py-24 text-center">
          <p className="text-gray-400 text-sm">No invoices found</p>
          <Link to="/batch-upload" className="mt-3 text-sm text-gray-900 hover:underline font-medium">
            Upload your first invoice →
          </Link>
        </div>
      ) : (
        <div ref={tableRef} className="flex-1 bg-white rounded-2xl border border-gray-200 overflow-hidden" style={{ minHeight: 0 }}>
          <div className="overflow-y-auto h-full">
            <table className="w-full">
              <thead className="sticky top-0 z-10 bg-white border-b border-gray-100">
                <tr>
                  <th className="w-10 px-4 py-3">
                    <button onClick={toggleAll} className="text-gray-300 hover:text-gray-600 transition-colors">
                      {allSelected ? <CheckSquare className="w-4 h-4 text-gray-700" /> : someSelected ? <Minus className="w-4 h-4 text-gray-400" /> : <Square className="w-4 h-4" />}
                    </button>
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-gray-400 uppercase tracking-wider">Invoice</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-gray-400 uppercase tracking-wider">Vendor</th>
                  <th className="text-right px-4 py-3 text-xs font-medium text-gray-400 uppercase tracking-wider">Amount</th>
                  <th className="text-center px-4 py-3 text-xs font-medium text-gray-400 uppercase tracking-wider">Status</th>
                  <th className="text-right px-4 py-3 text-xs font-medium text-gray-400 uppercase tracking-wider">Date</th>
                  <th className="w-10 px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {invoices.map((inv) => {
                  const isSelected = selected.has(inv.id);
                  return (
                    <tr
                      key={inv.id}
                      onClick={() => toggleOne(inv.id)}
                      className={`border-b border-gray-50 last:border-0 cursor-pointer select-none transition-colors ${
                        isSelected ? 'bg-gray-50' : 'hover:bg-gray-50/50'
                      }`}
                    >
                      <td className="px-4 py-3.5" onClick={e => e.stopPropagation()}>
                        <button onClick={() => toggleOne(inv.id)} className="text-gray-300 hover:text-gray-600 transition-colors">
                          {isSelected ? <CheckSquare className="w-4 h-4 text-gray-700" /> : <Square className="w-4 h-4" />}
                        </button>
                      </td>
                      <td className="px-4 py-3.5" onClick={e => e.stopPropagation()}>
                        <Link to={`/invoice/${inv.id}`} className="font-mono text-sm text-indigo-600 hover:text-indigo-800 hover:underline">
                          {inv.invoiceNumber || inv.id}
                        </Link>
                        {inv.invoiceNumber && <p className="text-xs text-gray-400 mt-0.5 font-mono">{inv.id}</p>}
                      </td>
                      <td className="px-4 py-3.5">
                        <span className="text-sm text-gray-600">{inv.vendorName || '—'}</span>
                      </td>
                      <td className="px-4 py-3.5 text-right">
                        <span className="text-sm font-medium text-gray-900">
                          {inv.totalAmount ? `₹${inv.totalAmount.toLocaleString('en-IN')}` : '—'}
                        </span>
                      </td>
                      <td className="px-4 py-3.5 text-center">
                        <StatusBadge status={inv.status as InvoiceStatus} />
                      </td>
                      <td className="px-4 py-3.5 text-right">
                        <span className="text-sm text-gray-400">
                          {new Date(inv.createdAt).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}
                        </span>
                      </td>
                      <td className="px-4 py-3.5 text-center" onClick={e => e.stopPropagation()}>
                        <button onClick={() => setDeleteTargets([inv.id])} className="text-gray-200 hover:text-red-400 transition-colors p-1 rounded">
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Floating selection bar */}
      {selected.size > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 flex items-center gap-3 bg-gray-900 text-white px-5 py-2.5 rounded-xl shadow-xl">
          <span className="text-sm font-medium">{selected.size} selected</span>
          <div className="w-px h-4 bg-gray-700" />
          <button onClick={() => setDeleteTargets([...selected])} className="text-sm text-red-400 hover:text-red-300 font-medium transition-colors flex items-center gap-1.5">
            <Trash2 className="w-3.5 h-3.5" /> Delete
          </button>
          <button onClick={() => setSelected(new Set())} className="text-sm text-gray-400 hover:text-gray-300 transition-colors">
            Clear
          </button>
        </div>
      )}
    </div>
  );
}