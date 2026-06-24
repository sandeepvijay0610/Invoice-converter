import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useInvoiceDetail } from '../hooks/useInvoiceDetail';
import { StatusBadge } from '../components/ui/StatusBadge';
import { LoadingSpinner } from '../components/ui/LoadingSpinner';
import { ArrowLeft, RotateCcw, Upload, Download, X, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import { invoiceApi } from '../api/invoices';

type ModalState = 'idle' | 'loading' | 'success' | 'error';

export default function InvoiceDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { invoice, loading, refresh } = useInvoiceDetail(id);

  const [showModal, setShowModal] = useState(false);
  const [modalState, setModalState] = useState<ModalState>('idle');
  const [sapResult, setSapResult] = useState<{ sapDocumentId?: string; message?: string; error?: string } | null>(null);

  const handleRetry = async () => {
    if (!id) return;
    await invoiceApi.retry(id);
    refresh();
  };

  const handleDownloadJson = () => {
    if (!invoice?.extractedPayload) return;
    const blob = new Blob([JSON.stringify(invoice.extractedPayload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${invoice.id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleExportToSAP = async () => {
    if (!id) return;
    setModalState('loading');
    try {
      const result = await invoiceApi.exportToSAP(id);
      setSapResult(result);
      setModalState('success');
      refresh(); // update status badge to SAP_EXPORTED
    } catch (err: any) {
      setSapResult({ error: err?.response?.data?.error || err?.message || 'Export failed' });
      setModalState('error');
    }
  };

  const openModal = () => {
    setModalState('idle');
    setSapResult(null);
    setShowModal(true);
  };

  const closeModal = () => {
    if (modalState === 'loading') return; // prevent close while in-flight
    setShowModal(false);
    setModalState('idle');
    setSapResult(null);
  };

  if (loading || !invoice) return <LoadingSpinner message="Loading invoice details..." />;

  const payload = invoice.extractedPayload;
  const header = payload?.header_data;
  const financial = payload?.financial_data;
  const lineItems = payload?.line_item_data || [];
  const canExport = invoice.status === 'READY FOR SAP';

  return (
    <div>
      {/* ── Header ── */}
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
          {(invoice.status === 'FAILED' || invoice.status === 'RATE LIMITED') && (
            <button onClick={handleRetry} className="inline-flex items-center gap-2 px-4 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 transition-colors text-sm font-medium">
              <RotateCcw className="w-4 h-4" /> Retry
            </button>
          )}
          {payload && canExport && (
            <button
              onClick={openModal}
              className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors text-sm font-medium"
            >
              <Upload className="w-4 h-4" /> Export to SAP
            </button>
          )}
          {invoice.status === 'SAP EXPORTED' && (
            <div className="inline-flex items-center gap-2 px-4 py-2 bg-emerald-50 text-emerald-700 border border-emerald-200 rounded-lg text-sm font-medium">
              <CheckCircle className="w-4 h-4" />
              Exported — {invoice.sapDocumentId || 'SAP Doc Created'}
            </div>
          )}
          <StatusBadge status={invoice.status} size="lg" />
        </div>
      </div>

      {/* ── Invoice content ── */}
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
                  {lineItems.map((item: any, i: number) => (
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

      {/* ── Export Modal ── */}
      {showModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ backgroundColor: 'rgba(0,0,0,0.45)' }}
          onClick={(e) => { if (e.target === e.currentTarget) closeModal(); }}
        >
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4 overflow-hidden">

            {/* Modal header */}
            <div className="flex items-center justify-between px-6 py-5 border-b border-gray-100">
              <h2 className="text-lg font-semibold text-gray-900">Export Invoice</h2>
              {modalState !== 'loading' && (
                <button onClick={closeModal} className="text-gray-400 hover:text-gray-600 transition-colors">
                  <X className="w-5 h-5" />
                </button>
              )}
            </div>

            {/* ── idle: show the two options ── */}
            {modalState === 'idle' && (
              <div className="p-6 space-y-3">
                <p className="text-sm text-gray-500 mb-4">
                  Choose how you want to export <span className="font-mono font-medium text-gray-700">{invoice.id}</span>
                </p>

                {/* Option 1: Download JSON */}
                <button
                  onClick={() => { handleDownloadJson(); closeModal(); }}
                  className="w-full flex items-center gap-4 p-4 rounded-xl border-2 border-gray-200 hover:border-indigo-400 hover:bg-indigo-50 transition-all group text-left"
                >
                  <div className="w-10 h-10 rounded-lg bg-gray-100 group-hover:bg-indigo-100 flex items-center justify-center flex-shrink-0 transition-colors">
                    <Download className="w-5 h-5 text-gray-600 group-hover:text-indigo-600" />
                  </div>
                  <div>
                    <p className="font-medium text-gray-900 text-sm">Download JSON</p>
                    <p className="text-xs text-gray-500 mt-0.5">Save the extracted SAP payload as a .json file</p>
                  </div>
                </button>

                {/* Option 2: Export to SAP */}
                <button
                  onClick={handleExportToSAP}
                  className="w-full flex items-center gap-4 p-4 rounded-xl border-2 border-gray-200 hover:border-emerald-400 hover:bg-emerald-50 transition-all group text-left"
                >
                  <div className="w-10 h-10 rounded-lg bg-gray-100 group-hover:bg-emerald-100 flex items-center justify-center flex-shrink-0 transition-colors">
                    <Upload className="w-5 h-5 text-gray-600 group-hover:text-emerald-600" />
                  </div>
                  <div>
                    <p className="font-medium text-gray-900 text-sm">Export to SAP S/4HANA</p>
                    <p className="text-xs text-gray-500 mt-0.5">POST to <code className="bg-gray-100 px-1 rounded">API_SUPPLIERINVOICE_PROCESS_SRV</code></p>
                  </div>
                </button>
              </div>
            )}

            {/* ── loading ── */}
            {modalState === 'loading' && (
              <div className="p-12 flex flex-col items-center gap-4">
                <Loader2 className="w-10 h-10 text-indigo-600 animate-spin" />
                <p className="text-sm font-medium text-gray-700">Posting to SAP S/4HANA...</p>
                <p className="text-xs text-gray-400">This may take a few seconds</p>
              </div>
            )}

            {/* ── success ── */}
            {modalState === 'success' && (
              <div className="p-8 flex flex-col items-center gap-4 text-center">
                <div className="w-14 h-14 rounded-full bg-emerald-100 flex items-center justify-center">
                  <CheckCircle className="w-8 h-8 text-emerald-600" />
                </div>
                <div>
                  <p className="font-semibold text-gray-900">Successfully Exported!</p>
                  <p className="text-sm text-gray-500 mt-1">{sapResult?.message}</p>
                </div>
                {sapResult?.sapDocumentId && (
                  <div className="w-full bg-emerald-50 border border-emerald-200 rounded-lg px-4 py-3">
                    <p className="text-xs text-emerald-600 font-medium uppercase tracking-wide mb-1">SAP Document Number</p>
                    <p className="text-lg font-mono font-bold text-emerald-800">{sapResult.sapDocumentId}</p>
                  </div>
                )}
                <button
                  onClick={closeModal}
                  className="mt-2 px-6 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition-colors text-sm font-medium"
                >
                  Done
                </button>
              </div>
            )}

            {/* ── error ── */}
            {modalState === 'error' && (
              <div className="p-8 flex flex-col items-center gap-4 text-center">
                <div className="w-14 h-14 rounded-full bg-red-100 flex items-center justify-center">
                  <AlertCircle className="w-8 h-8 text-red-500" />
                </div>
                <div>
                  <p className="font-semibold text-gray-900">Export Failed</p>
                  <p className="text-sm text-gray-500 mt-1">SAP returned an error</p>
                </div>
                <div className="w-full bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-left">
                  <p className="text-xs font-mono text-red-700 break-all">{sapResult?.error}</p>
                </div>
                <div className="flex gap-3 mt-2">
                  <button
                    onClick={closeModal}
                    className="px-4 py-2 border border-gray-200 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors text-sm font-medium"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => { setModalState('idle'); setSapResult(null); }}
                    className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors text-sm font-medium"
                  >
                    Try Again
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}