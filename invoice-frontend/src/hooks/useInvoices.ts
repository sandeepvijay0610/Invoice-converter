import { useState, useEffect, useCallback } from 'react';
import { invoiceApi } from '../api/invoices';
import type { InvoiceSummary } from '../types/invoice';

interface UseInvoicesReturn {
  invoices: InvoiceSummary[];
  loading: boolean;
  error: Error | null;
  statusFilter: string;
  setStatusFilter: (status: string) => void;
  refresh: () => void;
}

export function useInvoices(): UseInvoicesReturn {
  const [invoices, setInvoices] = useState<InvoiceSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [statusFilter, setStatusFilter] = useState('');

  const fetchInvoices = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await invoiceApi.list(statusFilter);
      setInvoices(data.items);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    fetchInvoices();
  }, [fetchInvoices]);

  return { invoices, loading, error, statusFilter, setStatusFilter, refresh: fetchInvoices };
}