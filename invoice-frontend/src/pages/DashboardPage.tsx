import { Link } from 'react-router-dom';
import { RefreshCw, Trash2, FileSpreadsheet } from 'lucide-react';
import { useInvoices } from '../hooks/useInvoices';
import { StatusBadge } from '../components/ui/StatusBadge';
import { LoadingSpinner } from '../components/ui/LoadingSpinner';
import { invoiceApi } from '../api/invoices';
import * as XLSX from 'xlsx';
import { useState } from 'react';

const STATUS_OPTIONS = [
  { value: '', label: 'All Status' },
  { value: 'READY_FOR_SAP', label: 'Ready for SAP' },
  { value: 'PROCESSING', label: 'Processing' },
  { value: 'REQUIRES_MANUAL_REVIEW', label: 'Needs Review' },
  { value: 'FAILED', label: 'Failed' },
  { value: 'RATE_LIMITED', label: 'Rate Limited' },
];

export default function DashboardPage() {
  const { invoices, loading, statusFilter, setStatusFilter, refresh } = useInvoices();
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await invoiceApi.delete(deleteTarget);
      refresh();
    } catch (err) {
      console.error('Delete failed:', err);
    } finally {
      setDeleteTarget(null);
    }
  };

  const exportAllToExcel = async () => {
    const summary = await invoiceApi.list('');
    const allIds = summary.items.map(inv => inv.id);
    const details = await Promise.all(allIds.map(id => invoiceApi.getById(id)));

    const summaryRows = details.map(inv => {
      const p = inv.extractedPayload;
      return {
        'Invoice ID': inv.id,
        'Status': inv.status,
        'Vendor Name': p?.header_data?.vendor_name || '',
        'Vendor GSTIN': p?.header_data?.vendor_gstin || '',
        'Buyer Name': p?.header_data?.buyer_name || '',
        'Buyer GSTIN': p?.header_data?.buyer_gstin || '',
        'Invoice Number': p?.header_data?.invoice_number || '',
        'Invoice Date': p?.header_data?.invoice_date || '',
        'PO Number': p?.header_data?.po_number || '',
        'Base Amount': p?.financial_data?.base_amount || 0,
        'CGST': p?.financial_data?.cgst_amount || 0,
        'SGST': p?.financial_data?.sgst_amount || 0,
        'IGST': p?.financial_data?.igst_amount || 0,
        'Total Invoice Amount': p?.financial_data?.total_invoice_amount || 0,
      };
    });

    const lineItemRows = details.flatMap(inv => {
      const p = inv.extractedPayload;
      const items = p?.line_item_data || [];
      return items.map((item, idx) => ({
        'Invoice ID': inv.id,
        'Line No': idx + 1,
        'Description': item.invoice_item_text || '',
        'HSN/SAC': item.hsn_sac_code || '',
        'Quantity': item.quantity || 0,
        'Unit Price': item.unit_price || 0,
        'Line Amount': item.line_amount || 0,
      }));
    });

    const wb = XLSX.utils.book_new();
    if (summaryRows.length > 0) {
      const ws1 = XLSX.utils.json_to_sheet(summaryRows);
      ws1['!cols'] = Object.keys(summaryRows[0]).map(k => ({ wch: Math.max(k.length, 15) }));
      XLSX.utils.book_append_sheet(wb, ws1, 'Summary');
    }
    if (lineItemRows.length > 0) {
      const ws2 = XLSX.utils.json_to_sheet(lineItemRows);
      ws2['!cols'] = Object.keys(lineItemRows[0]).map(k => ({ wch: Math.max(k.length, 15) }));
      XLSX.utils.book_append_sheet(wb, ws2, 'Line Items');
    }
    XLSX.writeFile(wb, 'All_Invoices.xlsx');
  };

  return (
    <div>
      {/* Spotlight Delete Modal */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" onClick={() => setDeleteTarget(null)} />
          <div className="relative bg-white rounded-2xl shadow-2xl p-6 w-full max-w-md">
            <h3 className="text-xl font-bold text-gray-900 mb-2">Delete Invoice</h3>
            <p className="text-gray-600 mb-6 text-sm">
              Delete invoice <span className="font-semibold">#{deleteTarget}</span>? This cannot be undone.
            </p>
            <div className="flex justify-end gap-3">
              <button onClick={() => setDeleteTarget(null)} className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg">Cancel</button>
              <button onClick={handleDelete} className="px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg">Delete</button>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Invoices</h1>
          <p className="text-sm text-gray-500 mt-1">Manage and track invoice processing</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={exportAllToExcel}
            className="inline-flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition-colors text-sm font-medium shadow-sm"
          >
            <FileSpreadsheet className="w-4 h-4" />
            Export All
          </button>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
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

      {/* Table */}
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
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden" style={{ height: 'calc(100vh - 180px)' }}>
          <div className="overflow-y-auto h-full">
            <table className="w-full">
              <thead className="sticky top-0 z-10">
                <tr className="border-b border-gray-200 bg-gray-50">
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase">Invoice #</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase">Vendor</th>
                  <th className="text-right px-6 py-3 text-xs font-semibold text-gray-500 uppercase">Amount</th>
                  <th className="text-center px-6 py-3 text-xs font-semibold text-gray-500 uppercase">Status</th>
                  <th className="text-right px-6 py-3 text-xs font-semibold text-gray-500 uppercase">Date</th>
                  <th className="text-center px-6 py-3 text-xs font-semibold text-gray-500 uppercase w-16"></th>
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
                      <button onClick={() => setDeleteTarget(inv.id)} className="text-gray-400 hover:text-red-600 transition-colors" title="Delete">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}