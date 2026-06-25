import { useState, useEffect, useCallback, useRef } from 'react';
import { invoiceApi } from '../api/invoices';
import type { InvoiceSummary } from '../types/invoice';

// Statuses that mean active work is happening — poll while any invoice has one
const ACTIVE_STATUSES = new Set(['PENDING', 'PROCESSING']);
const POLL_INTERVAL_MS = 5000;

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
  // Tracks first fetch so spinner only shows on mount, not background polls
  const isFirstFetch = useRef(true);

  const fetchInvoices = useCallback(async (showSpinner = false) => {
    if (showSpinner) setLoading(true);
    setError(null);
    try {
      const data = await invoiceApi.list(statusFilter);
      setInvoices(data.items);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
      isFirstFetch.current = false;
    }
  }, [statusFilter]);

  // Initial fetch with spinner
  useEffect(() => {
    isFirstFetch.current = true;
    fetchInvoices(true);
  }, [fetchInvoices]);

  // Background polling — only runs while at least one invoice is active.
  // Stops automatically when everything is READY_FOR_SAP / FAILED / etc.
  useEffect(() => {
    const hasActive = invoices.some(inv => ACTIVE_STATUSES.has(inv.status));
    if (!hasActive) return;

    const interval = setInterval(() => fetchInvoices(false), POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [invoices, fetchInvoices]);

  return {
    invoices,
    loading,
    error,
    statusFilter,
    setStatusFilter,
    refresh: () => fetchInvoices(true),
  };
}