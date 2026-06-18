import { useParams, Link } from 'react-router-dom';
import { useInvoiceDetail } from '../hooks/useInvoiceDetail';
import { StatusBadge } from '../components/ui/StatusBadge';
import { LoadingSpinner } from '../components/ui/LoadingSpinner';
import { ArrowLeft, RotateCcw, Download } from 'lucide-react';
import { invoiceApi } from '../api/invoices';

export default function InvoiceDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { invoice, loading, refresh } = useInvoiceDetail(id);

  const handleRetry = async () => {
    if (!id) return;
    await invoiceApi.retry(id);
    refresh();
  };

  const handleExport = () => {
    if (!invoice?.extractedPayload) return;
    const blob = new Blob([JSON.stringify(invoice.extractedPayload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `${invoice.id}.json`; a.click();
    URL.revokeObjectURL(url);
  };

  if (loading || !invoice) return <LoadingSpinner message="Loading invoice details..." />;

  const payload = invoice.extractedPayload;
  const header = payload?.header_data;
  const financial = payload?.financial_data;
  const lineItems = payload?.line_item_data || [];

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-4">
          <Link to="/" className="text-gray-500 hover:text-gray-700">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{invoice.id}</h1>
            <p className="text-sm text-gray-500 mt-1">Invoice details and extraction results</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {(invoice.status === 'FAILED' || invoice.status === 'RATE_LIMITED') && (
            <button onClick={handleRetry} className="inline-flex items-center gap-2 px-4 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 transition-colors text-sm font-medium">
              <RotateCcw className="w-4 h-4" /> Retry
            </button>
          )}
          {payload && (
            <button onClick={handleExport} className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors text-sm font-medium">
              <Download className="w-4 h-4" /> Export SAP JSON
            </button>
          )}
          <StatusBadge status={invoice.status} size="lg" />
        </div>
      </div>

      {payload && (
        <>
          <div className="grid grid-cols-2 gap-6 mb-6">
            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-4">Header Data</h2>
              <dl className="space-y-3">
                {[
                  ['Vendor', header?.vendor_name],
                  ['Vendor GSTIN', header?.vendor_gstin],
                  ['Buyer', header?.buyer_name],
                  ['Buyer GSTIN', header?.buyer_gstin],
                  ['Invoice Number', header?.invoice_number],
                  ['Invoice Date', header?.invoice_date],
                  ['PO Number', header?.po_number],
                ].map(([label, value]) => (
                  <div key={label} className="flex justify-between">
                    <dt className="text-sm text-gray-500">{label}</dt>
                    <dd className="text-sm font-medium text-gray-900 text-right">{value || '—'}</dd>
                  </div>
                ))}
              </dl>
            </div>

            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-4">Financial Data</h2>
              <dl className="space-y-3">
                {[
                  ['Base Amount', financial?.base_amount],
                  ['CGST', financial?.cgst_amount],
                  ['SGST', financial?.sgst_amount],
                  ['IGST', financial?.igst_amount],
                ].map(([label, value]) => (
                  <div key={label} className="flex justify-between">
                    <dt className="text-sm text-gray-500">{label}</dt>
                    <dd className="text-sm font-medium text-gray-900">₹{value?.toLocaleString('en-IN') || '0'}</dd>
                  </div>
                ))}
                <div className="pt-3 border-t border-gray-100 flex justify-between">
                  <dt className="text-sm font-semibold text-gray-700">Total</dt>
                  <dd className="text-lg font-bold text-emerald-600">₹{financial?.total_invoice_amount?.toLocaleString('en-IN') || '0'}</dd>
                </div>
              </dl>
            </div>
          </div>

          {lineItems.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <div className="px-6 py-4 border-b border-gray-100">
                <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Line Items</h2>
              </div>
              <table className="w-full">
                <thead>
                  <tr className="bg-gray-50">
                    <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase">Description</th>
                    <th className="text-center px-6 py-3 text-xs font-semibold text-gray-500 uppercase">HSN/SAC</th>
                    <th className="text-right px-6 py-3 text-xs font-semibold text-gray-500 uppercase">Qty</th>
                    <th className="text-right px-6 py-3 text-xs font-semibold text-gray-500 uppercase">Unit Price</th>
                    <th className="text-right px-6 py-3 text-xs font-semibold text-gray-500 uppercase">Amount</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {lineItems.map((item, i) => (
                    <tr key={i}>
                      <td className="px-6 py-3 text-sm text-gray-700">{item.invoice_item_text || '—'}</td>
                      <td className="px-6 py-3 text-sm text-gray-500 text-center font-mono">{item.hsn_sac_code || '—'}</td>
                      <td className="px-6 py-3 text-sm text-gray-700 text-right">{item.quantity || '—'}</td>
                      <td className="px-6 py-3 text-sm text-gray-700 text-right">₹{item.unit_price?.toLocaleString('en-IN') || '0'}</td>
                      <td className="px-6 py-3 text-sm font-medium text-gray-900 text-right">₹{item.line_amount?.toLocaleString('en-IN') || '0'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {!payload && (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
          <p className="text-gray-500">Extraction results not yet available</p>
          <p className="text-sm text-gray-400 mt-1">Status: {invoice.status}</p>
        </div>
      )}
    </div>
  );
}