import apiClient from './client';
import type { PaginatedResponse, InvoiceDetail, UploadResponse } from '../types/invoice';

export const invoiceApi = {
  requestUpload: (filename: string) =>
    apiClient.post<UploadResponse>('/invoices/request-upload', { filename }).then(r => r.data),

  uploadFile: (uploadUrl: string, file: File) =>
  fetch(uploadUrl, { 
    method: 'PUT', 
    body: file, 
    mode: 'no-cors',
    headers: { 'x-ms-blob-type': 'BlockBlob' } 
  }),

  process: (id: string) =>
    apiClient.post(`/invoices/${id}/process`),

  retry: (id: string) =>
    apiClient.post(`/invoices/${id}/retry`),

  list: (page = 0, status = '') =>
    apiClient.get<PaginatedResponse>('/invoices', { params: { page, size: 20, ...(status && { status }) } }).then(r => r.data),

  getById: (id: string) =>
    apiClient.get<InvoiceDetail>(`/invoices/${id}`).then(r => r.data),
};