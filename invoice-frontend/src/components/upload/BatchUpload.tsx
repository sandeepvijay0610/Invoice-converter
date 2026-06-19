import { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { useNavigate } from 'react-router-dom';
import { invoiceApi } from '../../api/invoices';
import { CheckCircle, XCircle, Loader2, Clock } from 'lucide-react';

interface FileProgress {
  file: File;
  id?: string;
  status: 'queued' | 'uploading' | 'processing' | 'done' | 'error';
  progress: string;
  error?: string;
}

export default function BatchUpload() {
  const [files, setFiles] = useState<FileProgress[]>([]);
  const [batchRunning, setBatchRunning] = useState(false);
  const navigate = useNavigate();

  const onDrop = useCallback((acceptedFiles: File[]) => {
    setFiles(prev => [
      ...prev,
      ...acceptedFiles.map(file => ({
        file,
        status: 'queued' as const,
        progress: 'Queued',
      }))
    ]);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'] },
    disabled: batchRunning,
  });

  const processBatch = async () => {
    setBatchRunning(true);
    
    for (let i = 0; i < files.length; i++) {
      const fileProgress = files[i];
      if (fileProgress.status === 'done') continue;

      setFiles(prev => prev.map((f, idx) => 
        idx === i ? { ...f, status: 'uploading', progress: 'Requesting upload...' } : f
      ));

      try {
        // Step 1: Request upload URL
        const { id, uploadUrl } = await invoiceApi.requestUpload(fileProgress.file.name);
        
        setFiles(prev => prev.map((f, idx) => 
          idx === i ? { ...f, id, status: 'uploading', progress: 'Uploading...' } : f
        ));

        // Step 2: Upload file
        await invoiceApi.uploadFile(uploadUrl, fileProgress.file);
        
        setFiles(prev => prev.map((f, idx) => 
          idx === i ? { ...f, status: 'processing', progress: 'AI extracting...' } : f
        ));

        // Step 3: Trigger processing
        await invoiceApi.process(id);
        
        setFiles(prev => prev.map((f, idx) => 
          idx === i ? { ...f, status: 'done', progress: 'Complete' } : f
        ));
        
      } catch (err: any) {
        setFiles(prev => prev.map((f, idx) => 
          idx === i ? { ...f, status: 'error', progress: 'Failed', error: err.message } : f
        ));
      }
    }
    
    setBatchRunning(false);
  };

  const removeFile = (index: number) => {
    setFiles(prev => prev.filter((_, i) => i !== index));
  };

  const statusIcon = (status: string) => {
    switch (status) {
      case 'done': return <CheckCircle className="w-5 h-5 text-emerald-500" />;
      case 'error': return <XCircle className="w-5 h-5 text-red-500" />;
      case 'uploading': case 'processing': return <Loader2 className="w-5 h-5 text-amber-500 animate-spin" />;
      default: return <Clock className="w-5 h-5 text-gray-400" />;
    }
  };

  const doneCount = files.filter(f => f.status === 'done').length;
  const errorCount = files.filter(f => f.status === 'error').length;
  const processingCount = files.filter(f => f.status === 'uploading' || f.status === 'processing').length;

  return (
    <div className="max-w-3xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Batch Upload</h1>
        <p className="text-sm text-gray-500 mt-1">Upload multiple invoices at once</p>
      </div>

      <div
        {...getRootProps()}
        className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all mb-6
          ${isDragActive ? 'border-indigo-500 bg-indigo-50' : 'border-gray-300 hover:border-gray-400'}
          ${batchRunning ? 'opacity-50 pointer-events-none' : ''}`}
      >
        <input {...getInputProps()} />
        <p className="text-gray-600">Drop PDF invoices here or click to browse</p>
        <p className="text-sm text-gray-400 mt-1">You can add more files after uploading</p>
      </div>

      {files.length > 0 && (
        <>
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden mb-4">
            <div className="px-6 py-3 bg-gray-50 border-b border-gray-100 flex justify-between items-center">
              <span className="text-sm font-medium text-gray-700">
                {files.length} file{files.length !== 1 ? 's' : ''}
                {doneCount > 0 && ` • ${doneCount} done`}
                {errorCount > 0 && ` • ${errorCount} failed`}
                {processingCount > 0 && ` • ${processingCount} processing`}
              </span>
              <button
                onClick={processBatch}
                disabled={batchRunning || files.every(f => f.status === 'done')}
                className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors"
              >
                {batchRunning ? 'Processing...' : 'Upload All'}
              </button>
            </div>
            <div className="divide-y divide-gray-100 max-h-96 overflow-y-auto">
              {files.map((fp, i) => (
                <div key={i} className="px-6 py-3 flex items-center gap-4">
                  {statusIcon(fp.status)}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-700 truncate">{fp.file.name}</p>
                    <p className="text-xs text-gray-500">{fp.progress}</p>
                    {fp.error && <p className="text-xs text-red-500 mt-0.5">{fp.error}</p>}
                  </div>
                  <div className="flex items-center gap-2">
                    {fp.status === 'done' && fp.id && (
                      <button
                        onClick={() => navigate(`/invoice/${fp.id}`)}
                        className="text-xs text-indigo-600 hover:text-indigo-800 font-medium"
                      >
                        View
                      </button>
                    )}
                    {fp.status !== 'uploading' && fp.status !== 'processing' && (
                      <button
                        onClick={() => removeFile(i)}
                        className="text-xs text-gray-400 hover:text-red-500"
                      >
                        Remove
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}