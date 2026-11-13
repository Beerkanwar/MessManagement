import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Icons } from './Icons';

export interface BreadcrumbItem {
  label: string;
  path: string;
}

const ROUTE_LABELS: Record<string, string> = {
  clerk: 'Hostel Clerk',
  admin: 'Super Admin',
  dashboard: 'Dashboard',
  verifications: 'Student Verification',
  menu: 'Menu',
  extras: 'Extra Items',
  bills: 'Bills',
  feedback: 'Feedback',
  reports: 'Reports',
  hostels: 'Hostels',
  messes: 'Messes',
  students: 'Students',
  clerks: 'Hostel Clerks',
  managers: 'Mess Managers',
  'meal-config': 'Meal Configuration',
  pricing: 'Pricing',
  billing: 'Billing',
  devices: 'Devices',
  sync: 'Synchronization',
  audit: 'Audit Logs',
  settings: 'System Configuration',
  gallery: 'Design Gallery',
};

export const Breadcrumbs: React.FC = () => {
  const location = useLocation();
  const segments = location.pathname.split('/').filter(Boolean);

  if (segments.length === 0) return null;

  let currentPath = '';
  const items: BreadcrumbItem[] = segments.map((seg) => {
    currentPath += `/${seg}`;
    return {
      label: ROUTE_LABELS[seg] || seg.charAt(0).toUpperCase() + seg.slice(1),
      path: currentPath,
    };
  });

  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-[12px] text-text-muted mb-3 select-none">
      <Link to="/" className="hover:text-text transition-colors">
        Home
      </Link>
      {items.map((item, index) => {
        const isLast = index === items.length - 1;
        return (
          <React.Fragment key={item.path}>
            <Icons.ChevronRight className="w-3.5 h-3.5 text-border-strong stroke-[2]" />
            {isLast ? (
              <span className="font-semibold text-text" aria-current="page">
                {item.label}
              </span>
            ) : (
              <Link to={item.path} className="hover:text-text transition-colors">
                {item.label}
              </Link>
            )}
          </React.Fragment>
        );
      })}
    </nav>
  );
};

