import { useInvoices } from '../hooks/useInvoices';
import { StatusBadge } from '../components/ui/StatusBadge';
import { LoadingSpinner } from '../components/ui/LoadingSpinner';
import { Link } from 'react-router-dom';
import { ChevronLeft, ChevronRight, RefreshCw, Trash2 } from 'lucide-react';
import { invoiceApi } from '../api/invoices';

const STATUS_OPTIONS = [
  { value: '', label: 'All Status' },
  { value: 'READY_FOR_SAP', label: 'Ready for SAP' },
  { value: 'PROCESSING', label: 'Processing' },
  { value: 'REQUIRES_MANUAL_REVIEW', label: 'Needs Review' },
  { value: 'FAILED', label: 'Failed' },
  { value: 'RATE_LIMITED', label: 'Rate Limited' },
];

export default function DashboardPage() {
  const { invoices, loading, page, totalPages, statusFilter, setPage, setStatusFilter, refresh } = useInvoices();

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this invoice permanently?')) return;
    try {
      await invoiceApi.delete(id);
      refresh();
    } catch (err) {
      console.error('Delete failed:', err);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Invoices</h1>
          <p className="text-sm text-gray-500 mt-1">Manage and track invoice processing</p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setPage(0); }}
            className="px-3 py-2 bg-white border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
          >
            {STATUS_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          <button onClick={refresh} className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors" title="Refresh">
            <RefreshCw className="w-5 h-5" />
          </button>
        </div>
      </div>

      {loading ? (
        <LoadingSpinner message="Loading invoices..." />
      ) : invoices.length === 0 ? (
        <div className="text-center py-16">
          <p className="text-gray-500 text-lg">No invoices found</p>
          <Link to="/batch-upload" className="inline-block mt-4 text-indigo-600 hover:text-indigo-700 font-medium">
            Upload your first invoice →
          </Link>
        </div>
      ) : (
        <>
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50">
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Invoice Number</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Vendor</th>
                  <th className="text-right px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Amount</th>
                  <th className="text-center px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Status</th>
                  <th className="text-right px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Date</th>
                  <th className="text-center px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {invoices.map((inv) => (
                  <tr key={inv.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-6 py-4">
                      <Link to={`/invoice/${inv.id}`} className="text-indigo-600 hover:text-indigo-800 font-mono text-sm">
                        {inv.invoiceNumber || inv.id}
                      </Link>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-700">{inv.vendorName || '—'}</td>
                    <td className="px-6 py-4 text-sm text-gray-900 text-right font-medium">
                      {inv.totalAmount ? `₹${inv.totalAmount.toLocaleString('en-IN')}` : '—'}
                    </td>
                    <td className="px-6 py-4 text-center">
                      <StatusBadge status={inv.status} />
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-500 text-right">
                      {new Date(inv.createdAt).toLocaleDateString('en-IN')}
                    </td>
                    <td className="px-6 py-4 text-center">
                      <button
                        onClick={(e) => { e.preventDefault(); handleDelete(inv.id); }}
                        className="text-gray-400 hover:text-red-600 transition-colors"
                        title="Delete invoice"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-6">
              <p className="text-sm text-gray-500">
                Page {page + 1} of {totalPages}
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage(page - 1)}
                  disabled={page === 0}
                  className="inline-flex items-center gap-1 px-3 py-2 text-sm border border-gray-300 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
                >
                  <ChevronLeft className="w-4 h-4" /> Previous
                </button>
                <button
                  onClick={() => setPage(page + 1)}
                  disabled={page >= totalPages - 1}
                  className="inline-flex items-center gap-1 px-3 py-2 text-sm border border-gray-300 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
                >
                  Next <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}