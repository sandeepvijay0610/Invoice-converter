import type { InvoiceStatus } from '../../types/invoice';

// Map from SNAKE_CASE status → display label + colour classes
const STATUS_CONFIG: Record<string, { label: string; className: string }> = {
  PENDING:                { label: 'Pending',        className: 'bg-yellow-50 text-yellow-700 ring-yellow-200' },
  PROCESSING:             { label: 'Processing',     className: 'bg-blue-50 text-blue-700 ring-blue-200' },
  READY_FOR_SAP:          { label: 'Ready for SAP',  className: 'bg-violet-50 text-violet-700 ring-violet-200' },
  SAP_EXPORTED:           { label: 'SAP Exported',   className: 'bg-emerald-50 text-emerald-700 ring-emerald-200' },
  FAILED:                 { label: 'Failed',         className: 'bg-red-50 text-red-700 ring-red-200' },
  RATE_LIMITED:           { label: 'Rate Limited',   className: 'bg-red-50 text-red-700 ring-red-200' },
  REQUIRES_MANUAL_REVIEW: { label: 'Needs Review',   className: 'bg-orange-50 text-orange-700 ring-orange-200' },
};

interface StatusBadgeProps {
  status: InvoiceStatus | string;
  size?: 'sm' | 'md' | 'lg';
}

export function StatusBadge({ status, size = 'md' }: StatusBadgeProps) {
  // Normalise — handles both SNAKE_CASE and legacy "SPACE CASE" strings
  const key = status.replace(/ /g, '_').toUpperCase();
  const config = STATUS_CONFIG[key] ?? { label: status, className: 'bg-gray-50 text-gray-600 ring-gray-200' };

  const sizeClass = size === 'sm'
    ? 'px-2 py-0.5 text-xs'
    : size === 'lg'
      ? 'px-3 py-1.5 text-sm'
      : 'px-2.5 py-0.5 text-xs';

  return (
    <span className={`inline-flex items-center font-medium rounded-full ring-1 ${config.className} ${sizeClass}`}>
      {config.label}
    </span>
  );
}