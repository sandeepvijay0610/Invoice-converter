import React from 'react';

interface StatusBadgeProps {
  status: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status }) => {
  // FIX: Normalize the string so "SAP EXPORTED" and "SAP_EXPORTED" are treated the exact same way
  const normalizedStatus = status.replace(/ /g, '_').toUpperCase();

  const getStatusStyles = (statusCode: string) => {
    switch (statusCode) {
      case 'PENDING':
        return 'bg-yellow-100 text-yellow-800 border-yellow-300 shadow-sm';
      case 'PROCESSING':
        return 'bg-blue-100 text-blue-800 border-blue-300 shadow-sm';
      case 'READY_FOR_SAP':
        return 'bg-purple-100 text-purple-800 border-purple-300 shadow-sm';
      case 'SAP_EXPORTED':
        return 'bg-emerald-100 text-emerald-800 border-emerald-300 shadow-sm';
      case 'FAILED':
      case 'RATE_LIMITED':
        return 'bg-red-100 text-red-800 border-red-300 shadow-sm';
      default:
        // The gray fallback
        return 'bg-gray-100 text-gray-800 border-gray-300 shadow-sm';
    }
  };

  const formatStatus = (rawStatus: string) => {
    // Replaces underscores with spaces so the UI always looks clean (e.g. "SAP EXPORTED")
    return rawStatus.replace(/_/g, ' ');
  };

  return (
    <span className={`px-3 py-1 rounded-full text-xs font-semibold border ${getStatusStyles(normalizedStatus)} uppercase tracking-wider`}>
      {formatStatus(status)}
    </span>
  );
};