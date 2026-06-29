import { Link, useLocation } from 'react-router-dom';
import { UserButton, useUser } from '@clerk/clerk-react';
import { LayoutDashboard, Upload, FileText } from 'lucide-react';
import clsx from 'clsx';
import type { ReactNode } from 'react';

const NAV_ITEMS = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/batch-upload', icon: Upload, label: 'Batch Upload' },
];

export function AppLayout({ children }: { children: ReactNode }) {
  const location = useLocation();
  const { user } = useUser();

  return (
    <div className="min-h-screen bg-gray-50 flex">
      <aside className="fixed left-0 top-0 h-full w-52 bg-white border-r border-gray-100 flex flex-col z-20">

        {/* Logo */}
        <div className="px-5 py-4 border-b border-gray-100">
          <Link to="/" className="flex items-center gap-2.5">
            <div className="w-7 h-7 bg-gray-900 rounded-lg flex items-center justify-center">
              <FileText className="w-3.5 h-3.5 text-white" />
            </div>
            <span className="font-semibold text-gray-900 text-sm">InvoiceFlow</span>
          </Link>
        </div>

        {/* Nav */}
        <nav className="flex-1 p-3 space-y-0.5">
          {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
            <Link
              key={to}
              to={to}
              className={clsx(
                'flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-all',
                location.pathname === to
                  ? 'bg-gray-900 text-white'
                  : 'text-gray-500 hover:text-gray-900 hover:bg-gray-50'
              )}
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {label}
            </Link>
          ))}
        </nav>

        {/* User */}
        <div className="p-3 border-t border-gray-100">
          <div className="flex items-center gap-2.5 px-2 py-2 rounded-lg hover:bg-gray-50 transition-colors">
            <UserButton />
            <div className="min-w-0">
              <p className="text-xs font-medium text-gray-700 truncate">
                {user?.fullName || 'User'}
              </p>
              <p className="text-xs text-gray-400 truncate">
                {user?.primaryEmailAddress?.emailAddress}
              </p>
            </div>
          </div>
        </div>
      </aside>

      <main className="ml-52 flex-1 p-6 min-h-screen">
        {children}
      </main>
    </div>
  );
}