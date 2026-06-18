import { useState, useEffect, useCallback } from 'react';
import { invoiceApi } from '../api/invoices';
import type { InvoiceDetail } from '../types/invoice';

export function useInvoiceDetail(id: string | undefined) {
  const [invoice, setInvoice] = useState<InvoiceDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const fetch = useCallback(async () => {
    if (!id) return;
    try {
      const data = await invoiceApi.getById(id);
      setInvoice(data);
      setError(null);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { fetch(); }, [fetch]);

  // Auto-poll while processing
  useEffect(() => {
    if (!invoice || (invoice.status !== 'PROCESSING' && invoice.status !== 'PENDING')) return;
    const interval = setInterval(fetch, 5000);
    return () => clearInterval(interval);
  }, [invoice?.status, fetch]);

  return { invoice, loading, error, refresh: fetch };
}