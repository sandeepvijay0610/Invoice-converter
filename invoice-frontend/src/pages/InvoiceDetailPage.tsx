import React, { useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, RotateCcw, Upload, Download, X, CheckCircle, AlertCircle, Loader2, FileText, Trash2, FileSpreadsheet } from 'lucide-react';
import toast from 'react-hot-toast';
import { invoiceApi } from '../api/invoices';
import { StatusBadge } from '../components/ui/StatusBadge';
import { LoadingSpinner } from '../components/ui/LoadingSpinner';
import * as XLSX from 'xlsx';

type ModalState = 'idle' | 'loading' | 'success' | 'error';

export default function InvoiceDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [showExportModal, setShowExportModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showPdfViewer, setShowPdfViewer] = useState(false);
  
  const [modalState, setModalState] = useState<ModalState>('idle');
  const [sapResult, setSapResult] = useState<{ sapDocumentId?: string; message?: string; error?: string } | null>(null);

  const { data: invoice, isLoading, isError } = useQuery({
    queryKey: ['invoice', id],
    queryFn: () => invoiceApi.getById(id!),
    enabled: !!id,
  });

  const deleteMutation = useMutation({
    mutationFn: () => invoiceApi.delete(id!),
    onSuccess: () => {
      toast.success('Invoice deleted successfully');
      queryClient.invalidateQueries({ queryKey: ['invoices'] });
      navigate('/dashboard');
    },
    onError: () => toast.error('Failed to delete invoice'),
  });

  const handleRetry = async () => {
    if (!id) return;
    await invoiceApi.retry(id);
    queryClient.invalidateQueries({ queryKey: ['invoice', id] });
    toast.success('Retry triggered');
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

  const handleDownloadExcel = () => {
    if (!invoice?.extractedPayload) return;
    const p = invoice.extractedPayload;

    const summary = [{
      'Invoice ID': invoice.id,
      'Status': invoice.status,
      'Vendor Name': p.header_data?.vendor_name || '',
      'Vendor GSTIN': p.header_data?.vendor_gstin || '',
      'Buyer Name': p.header_data?.buyer_name || '',
      'Buyer GSTIN': p.header_data?.buyer_gstin || '',
      'Invoice Number': p.header_data?.invoice_number || '',
      'Invoice Date': p.header_data?.invoice_date || '',
      'PO Number': p.header_data?.po_number || '',
      'Base Amount': p.financial_data?.base_amount || 0,
      'CGST': p.financial_data?.cgst_amount || 0,
      'SGST': p.financial_data?.sgst_amount || 0,
      'IGST': p.financial_data?.igst_amount || 0,
      'Total Invoice Amount': p.financial_data?.total_invoice_amount || 0,
    }];

    const items = p.line_item_data || [];
    const lineItems = items.map((item, idx) => ({
      'Line No': idx + 1,
      'Description': item.invoice_item_text || '',
      'HSN/SAC': item.hsn_sac_code || '',
      'Quantity': item.quantity || 0,
      'Unit Price': item.unit_price || 0,
      'Line Amount': item.line_amount || 0,
    }));

    const wb = XLSX.utils.book_new();
    const ws1 = XLSX.utils.json_to_sheet(summary);
    ws1['!cols'] = Object.keys(summary[0]).map(k => ({ wch: Math.max(k.length, 15) }));
    XLSX.utils.book_append_sheet(wb, ws1, 'Summary');
    if (lineItems.length > 0) {
      const ws2 = XLSX.utils.json_to_sheet(lineItems);
      ws2['!cols'] = Object.keys(lineItems[0]).map(k => ({ wch: Math.max(k.length, 15) }));
      XLSX.utils.book_append_sheet(wb, ws2, 'Line Items');
    }
    XLSX.writeFile(wb, `Invoice_${invoice.id}.xlsx`);
  };

  const handleExportToSAP = async () => {
    if (!id) return;
    setModalState('loading');
    try {
      const result = await invoiceApi.exportToSAP(id);
      setSapResult(result);
      setModalState('success');
      queryClient.invalidateQueries({ queryKey: ['invoice', id] });
    } catch (err: any) {
      setSapResult({ error: err?.response?.data?.error || err?.message || 'Export failed' });
      setModalState('error');
    }
  };

  const openExportModal = () => { setModalState('idle'); setSapResult(null); setShowExportModal(true); };
  const closeExportModal = () => { if (modalState === 'loading') return; setShowExportModal(false); setModalState('idle'); setSapResult(null); };

  if (isLoading || !invoice) return <LoadingSpinner message="Loading invoice details..." />;
  if (isError) return <div className="p-8 text-center text-red-500">Failed to load invoice details.</div>;

  const payload = invoice.extractedPayload;
  const header = payload?.header_data;
  const financial = payload?.financial_data;
  const lineItems = payload?.line_item_data || [];
  
  const normalizedStatus = invoice.status.replace(/_/g, ' ');
  const isSapExported = normalizedStatus === 'SAP EXPORTED';
  const canExport = normalizedStatus === 'READY FOR SAP' || isSapExported;
  const fileName = invoice.filePath ? invoice.filePath.split('/').pop() : `Invoice_${invoice.id}.pdf`;
  const pdfUrl = invoice.filePath?.startsWith('http') ? invoice.filePath : `http://127.0.0.1:10000/devstoreaccount1/invoices/${fileName}`;

  return (
    <div className="max-w-6xl mx-auto p-4 md:p-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between mb-8 gap-4">
        <div className="flex items-center gap-4">
          <Link to="/" className="text-gray-500 hover:text-gray-700"><ArrowLeft className="w-5 h-5" /></Link>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{invoice.id}</h1>
            <p className="text-sm text-gray-500 mt-1">Invoice details and extraction results</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <StatusBadge status={invoice.status} />
          {(invoice.status === 'FAILED' || invoice.status === 'RATE LIMITED') && (
            <button onClick={handleRetry} className="inline-flex items-center gap-2 px-4 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 transition-colors text-sm font-medium shadow-sm">
              <RotateCcw className="w-4 h-4" /> Retry
            </button>
          )}
          <button onClick={() => setShowPdfViewer(true)} className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-50 text-indigo-700 border border-indigo-200 rounded-lg hover:bg-indigo-100 transition-colors text-sm font-medium">
            <FileText className="w-4 h-4" /> View PDF
          </button>
          {payload && canExport && (
            <button onClick={openExportModal} className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium shadow-sm">
              <Upload className="w-4 h-4" /> {isSapExported ? 'Re-export' : 'Export'}
            </button>
          )}
          <button onClick={() => setShowDeleteModal(true)} className="inline-flex items-center gap-2 px-4 py-2 bg-red-50 text-red-600 border border-red-200 rounded-lg hover:bg-red-100 transition-colors text-sm font-medium">
            <Trash2 className="w-4 h-4" /> Delete
          </button>
        </div>
      </div>

      {isSapExported && (
        <div className="mb-6 p-4 bg-emerald-50 border border-emerald-200 rounded-xl flex items-center justify-between">
          <div className="flex items-center gap-3">
            <CheckCircle className="w-5 h-5 text-emerald-600" />
            <div>
              <p className="text-sm font-semibold text-emerald-800">Exported to SAP S/4HANA</p>
              <p className="text-xs text-emerald-600 mt-0.5">Document successfully created</p>
            </div>
          </div>
        </div>
      )}

      {/* Invoice Content */}
      {payload ? (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
            <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
              <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-4">Header Data</h2>
              <dl className="space-y-3">
                {[['Vendor', header?.vendor_name],['Vendor GSTIN', header?.vendor_gstin],['Buyer', header?.buyer_name],['Buyer GSTIN', header?.buyer_gstin],['Invoice Number', header?.invoice_number],['Invoice Date', header?.invoice_date],['PO Number', header?.po_number]].map(([l,v]) => (
                  <div key={l} className="flex justify-between border-b border-gray-50 pb-2 last:border-0 last:pb-0">
                    <dt className="text-sm text-gray-500">{l}</dt><dd className="text-sm font-medium text-gray-900 text-right">{v || '—'}</dd>
                  </div>
                ))}
              </dl>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
              <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-4">Financial Data</h2>
              <dl className="space-y-3">
                {[['Base Amount', financial?.base_amount],['CGST', financial?.cgst_amount],['SGST', financial?.sgst_amount],['IGST', financial?.igst_amount]].map(([l,v]) => (
                  <div key={l} className="flex justify-between border-b border-gray-50 pb-2">
                    <dt className="text-sm text-gray-500">{l}</dt><dd className="text-sm font-medium text-gray-900">₹{v?.toLocaleString('en-IN') || '0'}</dd>
                  </div>
                ))}
                <div className="pt-2 flex justify-between">
                  <dt className="text-sm font-semibold text-gray-700">Total</dt><dd className="text-lg font-bold text-emerald-600">₹{financial?.total_invoice_amount?.toLocaleString('en-IN') || '0'}</dd>
                </div>
              </dl>
            </div>
          </div>
          {lineItems.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
              <div className="px-6 py-4 border-b border-gray-100"><h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Line Items</h2></div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead><tr className="bg-gray-50"><th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase">Description</th><th className="text-center px-6 py-3 text-xs font-semibold text-gray-500 uppercase">HSN/SAC</th><th className="text-right px-6 py-3 text-xs font-semibold text-gray-500 uppercase">Qty</th><th className="text-right px-6 py-3 text-xs font-semibold text-gray-500 uppercase">Unit Price</th><th className="text-right px-6 py-3 text-xs font-semibold text-gray-500 uppercase">Amount</th></tr></thead>
                  <tbody className="divide-y divide-gray-100">
                    {lineItems.map((item: any, i: number) => (
                      <tr key={i} className="hover:bg-gray-50">
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
            </div>
          )}
        </>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center shadow-sm"><p className="text-gray-500 font-medium">Extraction results not yet available</p><p className="text-sm text-gray-400 mt-1">Current Status: {invoice.status}</p></div>
      )}

      {/* Export Modal */}
      {showExportModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" onClick={closeExportModal} />
          <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4 overflow-hidden">
            <div className="flex items-center justify-between px-6 py-5 border-b border-gray-100">
              <h2 className="text-lg font-semibold text-gray-900">Export Options</h2>
              {modalState !== 'loading' && <button onClick={closeExportModal} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>}
            </div>
            {modalState === 'idle' && (
              <div className="p-6 space-y-3">
                <p className="text-sm text-gray-500 mb-4">Choose how you want to export <span className="font-mono font-medium text-gray-700">{invoice.id}</span></p>
                <button onClick={() => { handleDownloadJson(); closeExportModal(); }} className="w-full flex items-center gap-4 p-4 rounded-xl border-2 border-gray-200 hover:border-indigo-400 hover:bg-indigo-50 transition-all group text-left">
                  <div className="w-10 h-10 rounded-lg bg-gray-100 group-hover:bg-indigo-100 flex items-center justify-center"><Download className="w-5 h-5 text-gray-600 group-hover:text-indigo-600" /></div>
                  <div><p className="font-medium text-gray-900 text-sm">Download JSON</p><p className="text-xs text-gray-500 mt-0.5">Save the extracted payload locally</p></div>
                </button>
                <button onClick={() => { handleDownloadExcel(); closeExportModal(); }} className="w-full flex items-center gap-4 p-4 rounded-xl border-2 border-gray-200 hover:border-green-400 hover:bg-green-50 transition-all group text-left">
                  <div className="w-10 h-10 rounded-lg bg-gray-100 group-hover:bg-green-100 flex items-center justify-center"><FileSpreadsheet className="w-5 h-5 text-gray-600 group-hover:text-green-600" /></div>
                  <div><p className="font-medium text-gray-900 text-sm">Export to Excel</p><p className="text-xs text-gray-500 mt-0.5">Download summary and line items as .xlsx</p></div>
                </button>
                <button onClick={handleExportToSAP} className="w-full flex items-center gap-4 p-4 rounded-xl border-2 border-gray-200 hover:border-emerald-400 hover:bg-emerald-50 transition-all group text-left">
                  <div className="w-10 h-10 rounded-lg bg-gray-100 group-hover:bg-emerald-100 flex items-center justify-center"><Upload className="w-5 h-5 text-gray-600 group-hover:text-emerald-600" /></div>
                  <div><p className="font-medium text-gray-900 text-sm">Export to SAP S/4HANA</p><p className="text-xs text-gray-500 mt-0.5">POST to API_SUPPLIERINVOICE_PROCESS_SRV</p></div>
                </button>
              </div>
            )}
            {modalState === 'loading' && (<div className="p-12 flex flex-col items-center gap-4"><Loader2 className="w-10 h-10 text-indigo-600 animate-spin" /><p className="text-sm font-medium text-gray-700">Posting to SAP S/4HANA...</p></div>)}
            {modalState === 'success' && (
              <div className="p-8 flex flex-col items-center gap-4 text-center">
                <div className="w-14 h-14 rounded-full bg-emerald-100 flex items-center justify-center"><CheckCircle className="w-8 h-8 text-emerald-600" /></div>
                <div><p className="font-semibold text-gray-900">Successfully Exported!</p><p className="text-sm text-gray-500 mt-1">{sapResult?.message}</p></div>
                {sapResult?.sapDocumentId && (<div className="w-full bg-emerald-50 border border-emerald-200 rounded-lg px-4 py-3"><p className="text-xs text-emerald-600 font-medium uppercase mb-1">SAP Document Number</p><p className="text-lg font-mono font-bold text-emerald-800">{sapResult.sapDocumentId}</p></div>)}
                <button onClick={closeExportModal} className="mt-2 px-6 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition-colors text-sm font-medium">Done</button>
              </div>
            )}
            {modalState === 'error' && (
              <div className="p-8 flex flex-col items-center gap-4 text-center">
                <div className="w-14 h-14 rounded-full bg-red-100 flex items-center justify-center"><AlertCircle className="w-8 h-8 text-red-500" /></div>
                <div><p className="font-semibold text-gray-900">Export Failed</p><p className="text-sm text-gray-500 mt-1">SAP returned an error</p></div>
                <div className="w-full bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-left"><p className="text-xs font-mono text-red-700 break-all">{sapResult?.error}</p></div>
                <div className="flex gap-3 mt-2">
                  <button onClick={closeExportModal} className="px-4 py-2 border border-gray-200 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors text-sm font-medium">Cancel</button>
                  <button onClick={() => { setModalState('idle'); setSapResult(null); }} className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors text-sm font-medium">Try Again</button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Delete Modal */}
      {showDeleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" onClick={() => setShowDeleteModal(false)} />
          <div className="relative bg-white rounded-2xl shadow-2xl p-6 w-full max-w-md">
            <h3 className="text-xl font-bold text-gray-900 mb-2">Delete Invoice</h3>
            <p className="text-gray-600 mb-6 text-sm">Delete invoice <span className="font-semibold text-gray-900">#{invoice.id}</span>? This cannot be undone.</p>
            <div className="flex justify-end gap-3">
              <button onClick={() => setShowDeleteModal(false)} disabled={deleteMutation.isPending} className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg">Cancel</button>
              <button onClick={() => deleteMutation.mutate()} disabled={deleteMutation.isPending} className="px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg">{deleteMutation.isPending ? 'Deleting...' : 'Confirm Delete'}</button>
            </div>
          </div>
        </div>
      )}

      {/* PDF Viewer */}
      {showPdfViewer && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" onClick={() => setShowPdfViewer(false)} />
          <div className="relative flex flex-col bg-white rounded-2xl shadow-2xl w-full max-w-5xl h-[90vh] overflow-hidden">
            <div className="flex justify-between items-center p-4 border-b border-gray-200">
              <div className="flex items-center gap-4"><h3 className="text-lg text-gray-900 font-semibold">Document Viewer</h3><span className="bg-gray-100 text-gray-500 px-3 py-1 rounded-md text-xs font-mono">{fileName}</span></div>
              <button onClick={() => setShowPdfViewer(false)} className="text-gray-400 hover:text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-full p-2"><X className="w-5 h-5" /></button>
            </div>
            <div className="flex-grow"><iframe src={pdfUrl} className="w-full h-full border-none" title="PDF Document Viewer" /></div>
          </div>
        </div>
      )}
    </div>
  );
}