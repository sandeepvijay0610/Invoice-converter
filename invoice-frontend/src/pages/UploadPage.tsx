import { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { useNavigate } from 'react-router-dom';
import { invoiceApi } from '../api/invoices';
import { Upload, FileText, CheckCircle, AlertCircle } from 'lucide-react';

type UploadState = 'idle' | 'requesting' | 'uploading' | 'processing' | 'done' | 'error';

export default function UploadPage() {
  const [state, setState] = useState<UploadState>('idle');
  const [progress, setProgress] = useState('');
  const [invoiceId, setInvoiceId] = useState('');
  const navigate = useNavigate();

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    const file = acceptedFiles[0];
    if (!file) return;

    try {
      setState('requesting');
      setProgress('Preparing secure upload...');
      const { id, uploadUrl } = await invoiceApi.requestUpload(file.name);

      setState('uploading');
      setProgress('Uploading document...');
      await invoiceApi.uploadFile(uploadUrl, file);

      setState('processing');
      setProgress('Starting AI extraction...');
      await invoiceApi.process(id);
      setInvoiceId(id);

      setState('done');
      setTimeout(() => navigate(`/invoice/${id}`), 1500);
    } catch (err) {
      setState('error');
      const message =
        (err as any)?.response?.data?.error ||
        (err as any)?.response?.data?.message ||
        'Upload failed. Please try again.';
      setProgress(message);
    }
  }, [navigate]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'] },
    maxFiles: 1,
    disabled: state !== 'idle' && state !== 'error',
  });

  return (
    <div className="max-w-2xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Upload Invoice</h1>
        <p className="text-sm text-gray-500 mt-1">Upload a PDF invoice for AI-powered data extraction</p>
      </div>

      <div
        {...getRootProps()}
        className={`
          relative border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-all
          ${isDragActive ? 'border-indigo-500 bg-indigo-50' : 'border-gray-300 hover:border-gray-400 bg-white'}
          ${state === 'uploading' || state === 'requesting' || state === 'processing' ? 'pointer-events-none opacity-75' : ''}
        `}
      >
        <input {...getInputProps()} />

        {state === 'idle' && (
          <div>
            <Upload className="w-12 h-12 text-gray-400 mx-auto mb-4" />
            <p className="text-lg font-medium text-gray-700">Drop your invoice PDF here</p>
            <p className="text-sm text-gray-500 mt-1">or click to browse files</p>
          </div>
        )}

        {state === 'requesting' && (
          <div className="animate-pulse">
            <FileText className="w-12 h-12 text-indigo-400 mx-auto mb-4" />
            <p className="text-lg text-gray-600">{progress}</p>
          </div>
        )}

        {state === 'uploading' && (
          <div>
            <div className="w-16 h-16 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin mx-auto mb-4" />
            <p className="text-lg text-gray-600">{progress}</p>
          </div>
        )}

        {state === 'processing' && (
          <div>
            <div className="w-16 h-16 border-4 border-amber-200 border-t-amber-600 rounded-full animate-spin mx-auto mb-4" />
            <p className="text-lg text-gray-600">{progress}</p>
          </div>
        )}

        {state === 'done' && (
          <div>
            <CheckCircle className="w-12 h-12 text-emerald-500 mx-auto mb-4" />
            <p className="text-lg font-medium text-emerald-700">Upload successful!</p>
            <p className="text-sm text-gray-500 mt-1">Redirecting to invoice details...</p>
          </div>
        )}

        {state === 'error' && (
          <div>
            <AlertCircle className="w-12 h-12 text-red-400 mx-auto mb-4" />
            <p className="text-lg text-red-600">{progress}</p>
            <button
              onClick={(e) => { e.stopPropagation(); setState('idle'); }}
              className="mt-4 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
            >
              Try Again
            </button>
          </div>
        )}
      </div>

      <div className="mt-8 bg-white rounded-xl border border-gray-200 p-6">
        <h3 className="font-semibold text-gray-900 mb-3">Requirements</h3>
        <ul className="space-y-2 text-sm text-gray-600">
          <li className="flex items-center gap-2">• PDF format only</li>
          <li className="flex items-center gap-2">• Maximum file size: 25MB</li>
          <li className="flex items-center gap-2">• Indian GST invoices supported</li>
          <li className="flex items-center gap-2">• Multi-page documents accepted</li>
        </ul>
      </div>
    </div>
  );
}