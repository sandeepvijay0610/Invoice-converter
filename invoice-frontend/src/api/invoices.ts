import apiClient from './client';
import type { PaginatedResponse, InvoiceDetail, UploadResponse } from '../types/invoice';

export const invoiceApi = {
  requestUpload: (filename: string) =>
    apiClient.post<UploadResponse>('/invoices/request-upload', { filename }).then(r => r.data),

  uploadFile: (uploadUrl: string, file: File) =>
    fetch(uploadUrl, { method: 'PUT', body: file, headers: { 'x-ms-blob-type': 'BlockBlob' } }),

  process: (id: string) =>
    apiClient.post(`/invoices/${id}/process`),

  retry: (id: string) =>
    apiClient.post(`/invoices/${id}/retry`),

  delete: (id: string) =>
    apiClient.delete(`/invoices/${id}`),

  list: (status = '') =>
    apiClient.get<PaginatedResponse>('/invoices', { 
      params: { 
        page: 0, 
        size: 1000, 
        ...(status && { status }) 
      } 
    }).then(r => r.data),

  getById: (id: string) =>
    apiClient.get<InvoiceDetail>(`/invoices/${id}`).then(r => r.data),

  exportToSAP: (id: string) =>
    apiClient.post(`/invoices/${id}/export-sap`).then(r => r.data),
};