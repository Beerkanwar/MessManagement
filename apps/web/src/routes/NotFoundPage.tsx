import React from 'react';
import { Link } from 'react-router-dom';
import { Icons } from '../components/Icons';
import { Button } from '../components/Button';

export const NotFoundPage: React.FC = () => {
  return (
    <div className="min-h-[70vh] flex flex-col items-center justify-center text-center p-6 select-none">
      <div className="w-16 h-16 rounded-full bg-bg border border-border text-text-muted flex items-center justify-center mb-4">
        <Icons.Search className="w-8 h-8 stroke-[1.75]" />
      </div>
      <span className="text-[12px] font-bold text-text-muted tracking-wider uppercase mb-1">
        404 Not Found
      </span>
      <h2 className="text-[24px] font-bold text-text mb-2">Page Not Found</h2>
      <p className="text-[14px] text-text-secondary max-w-md mb-6">
        The URL path you requested does not exist or has been moved.
      </p>
      <Link to="/">
        <Button variant="secondary" icon={<Icons.ChevronLeft className="w-4 h-4" />}>
          Return to Dashboard
        </Button>
      </Link>
    </div>
  );
};
export default NotFoundPage;

