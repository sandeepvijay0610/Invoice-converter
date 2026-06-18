import clsx from 'clsx';

const STATUS_STYLES: Record<string, string> = {
  READY_FOR_SAP: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  PROCESSING: 'bg-amber-100 text-amber-800 border-amber-200',
  PENDING: 'bg-slate-100 text-slate-600 border-slate-200',
  REQUIRES_MANUAL_REVIEW: 'bg-red-100 text-red-800 border-red-200',
  FAILED: 'bg-red-100 text-red-800 border-red-200',
  RATE_LIMITED: 'bg-purple-100 text-purple-800 border-purple-200',
};

const STATUS_LABELS: Record<string, string> = {
  READY_FOR_SAP: 'Ready for SAP',
  PROCESSING: 'Processing',
  PENDING: 'Pending',
  REQUIRES_MANUAL_REVIEW: 'Needs Review',
  FAILED: 'Failed',
  RATE_LIMITED: 'Rate Limited',
};

export function StatusBadge({ status, size = 'sm' }: { status: string; size?: 'sm' | 'lg' }) {
  return (
    <span className={clsx(
      'inline-flex items-center border rounded-full font-medium',
      size === 'lg' ? 'px-3 py-1 text-sm' : 'px-2.5 py-0.5 text-xs',
      STATUS_STYLES[status] || 'bg-gray-100 text-gray-600 border-gray-200'
    )}>
      {STATUS_LABELS[status] || status}
    </span>
  );
}