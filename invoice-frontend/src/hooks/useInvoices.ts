import { useState, useEffect, useCallback } from 'react';
import { invoiceApi } from '../api/invoices';
import type { InvoiceSummary } from '../types/invoice';

interface UseInvoicesReturn {
  invoices: InvoiceSummary[];
  loading: boolean;
  error: Error | null;
  page: number;
  totalPages: number;
  statusFilter: string;
  setPage: (page: number) => void;
  setStatusFilter: (status: string) => void;
  refresh: () => void;
}

export function useInvoices(): UseInvoicesReturn {
  const [invoices, setInvoices] = useState<InvoiceSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [page, setPage] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [statusFilter, setStatusFilter] = useState('');

  const fetchInvoices = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await invoiceApi.list(page, statusFilter);
      setInvoices(data.items);
      setTotalPages(data.totalPages);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter]);

  useEffect(() => { fetchInvoices(); }, [fetchInvoices]);

  return { invoices, loading, error, page, totalPages, statusFilter, setPage, setStatusFilter, refresh: fetchInvoices };
}