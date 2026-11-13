import React, { useState } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { useAuth } from '../../state/auth';
import { Button } from '../../components/Button';
import { TextField } from '../../components/TextField';
import { PasswordField } from '../../components/PasswordField';
import { WrongClientNotice } from '../../components/WrongClientNotice';
import { AppError } from '../../api/errors';

export const SignInPage: React.FC = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [showWrongClient, setShowWrongClient] = useState(false);
  const { login, isLoading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const from = (location.state as any)?.from?.pathname;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setShowWrongClient(false);

    try {
      const response = await login(email, password);
      // Route based on role
      if (response.role === 'SUPER_ADMIN') {
        navigate(from || '/admin/dashboard', { replace: true });
      } else if (response.role === 'HOSTEL_CLERK') {
        navigate(from || '/clerk/dashboard', { replace: true });
      } else {
        setShowWrongClient(true);
      }
    } catch (err: any) {
      if (err instanceof AppError && err.code === 'WRONG_CLIENT') {
        setShowWrongClient(true);
      } else {
        setErrorMsg(err.message || 'Invalid email or password. Please try again.');
      }
    }
  };

  if (showWrongClient) {
    return <WrongClientNotice onBackToLogin={() => setShowWrongClient(false)} />;
  }

  return (
    <div className="min-h-screen bg-bg flex flex-col justify-center py-12 sm:px-6 lg:px-8 select-none">
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center">
        <div className="w-12 h-12 rounded-[10px] bg-primary flex items-center justify-center text-white font-bold text-[18px] mx-auto shadow-sm">
          HM
        </div>
        <h2 className="mt-4 text-[26px] font-bold text-text tracking-tight">
          Hostel Mess Portal
        </h2>
        <p className="mt-1 text-[14px] text-text-secondary">
          Staff authentication for Hostel Clerks and Super Administrators
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-surface py-8 px-6 shadow-sm border border-border rounded-[16px] sm:px-10">
          <form className="space-y-5" onSubmit={handleSubmit}>
            {errorMsg && (
              <div
                role="alert"
                className="p-3 rounded-[6px] bg-danger-subtle border border-danger/30 text-danger text-[13px] font-medium"
              >
                {errorMsg}
              </div>
            )}

            <TextField
              label="College Email Address"
              type="email"
              required
              autoComplete="email"
              placeholder="admin@college.edu"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-[13px] font-medium text-text">Password</label>
                <Link
                  to="/forgot-password"
                  className="text-[12px] font-medium text-primary hover:underline"
                >
                  Forgot password?
                </Link>
              </div>
              <PasswordField
                required
                autoComplete="current-password"
                placeholder="Enter password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>

            <Button
              type="submit"
              variant="primary"
              loading={isLoading}
              className="w-full justify-center min-h-[48px] text-[15px]"
            >
              Sign In to Portal
            </Button>
          </form>

          <div className="mt-6 pt-6 border-t border-border text-center">
            <p className="text-[12px] text-text-muted">
              Are you a Student or Mess Manager?{' '}
              <button
                type="button"
                onClick={() => setShowWrongClient(true)}
                className="text-primary font-medium hover:underline inline"
              >
                Use the Mobile App
              </button>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
export default SignInPage;

