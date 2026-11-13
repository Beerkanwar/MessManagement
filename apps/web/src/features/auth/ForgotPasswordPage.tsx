import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button } from '../../components/Button';
import { TextField } from '../../components/TextField';
import { PasswordField } from '../../components/PasswordField';
import { Stepper } from '../../components/Stepper';
import { apiClient } from '../../api/client';
import { Icons } from '../../components/Icons';

export const ForgotPasswordPage: React.FC = () => {
  const [step, setStep] = useState(0); // 0: Email, 1: OTP, 2: New Password
  const [email, setEmail] = useState('');
  const [otp, setOtp] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const navigate = useNavigate();

  const handleSendOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setErrorMsg(null);
    try {
      await apiClient.post('/auth/forgot-password', { email });
      setStep(1);
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to dispatch verification code.');
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setErrorMsg(null);
    try {
      await apiClient.post('/auth/verify-otp', { email, otp });
      setStep(2);
    } catch (err: any) {
      setErrorMsg(err.message || 'Invalid or expired OTP code.');
    } finally {
      setLoading(false);
    }
  };

  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setErrorMsg(null);
    try {
      await apiClient.post('/auth/reset-password', {
        email,
        otp,
        new_password: newPassword,
      });
      setSuccessMsg('Your password has been reset successfully. Redirecting to sign in...');
      setTimeout(() => navigate('/login'), 2000);
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to update password.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-bg flex flex-col justify-center py-12 sm:px-6 lg:px-8 select-none">
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center">
        <h2 className="text-[24px] font-bold text-text">Password Reset</h2>
        <p className="mt-1 text-[13px] text-text-secondary">
          Follow the 3-step verification flow to securely restore access
        </p>
      </div>

      <div className="mt-6 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-surface py-8 px-6 shadow-sm border border-border rounded-[16px] sm:px-10">
          <div className="mb-6">
            <Stepper
              currentStep={step}
              steps={[
                { id: 'email', label: 'Email' },
                { id: 'otp', label: 'OTP' },
                { id: 'pass', label: 'Password' },
              ]}
            />
          </div>

          {errorMsg && (
            <div role="alert" className="p-3 mb-4 rounded bg-danger-subtle text-danger text-[13px] font-medium border border-danger/30">
              {errorMsg}
            </div>
          )}

          {successMsg && (
            <div role="status" className="p-3 mb-4 rounded bg-success-subtle text-success text-[13px] font-medium border border-success/30">
              {successMsg}
            </div>
          )}

          {step === 0 && (
            <form onSubmit={handleSendOtp} className="space-y-4">
              <TextField
                label="Registered College Email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="clerk@hostel.college.edu"
              />
              <Button type="submit" variant="primary" loading={loading} className="w-full justify-center">
                Send Verification OTP
              </Button>
            </form>
          )}

          {step === 1 && (
            <form onSubmit={handleVerifyOtp} className="space-y-4">
              <p className="text-[13px] text-text-secondary">
                We dispatched a 6-digit code to <strong>{email}</strong>.
              </p>
              <TextField
                label="6-Digit Verification Code"
                required
                maxLength={6}
                value={otp}
                onChange={(e) => setOtp(e.target.value)}
                placeholder="123456"
                className="text-center font-mono text-[18px] tracking-widest"
              />
              <Button type="submit" variant="primary" loading={loading} className="w-full justify-center">
                Verify Code
              </Button>
            </form>
          )}

          {step === 2 && (
            <form onSubmit={handleResetPassword} className="space-y-4">
              <PasswordField
                label="New Password"
                required
                minLength={10}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                helperText="Minimum 10 characters"
              />
              <Button type="submit" variant="primary" loading={loading} className="w-full justify-center">
                Set New Password
              </Button>
            </form>
          )}

          <div className="mt-6 pt-4 border-t border-border text-center">
            <Link to="/login" className="inline-flex items-center gap-1 text-[13px] text-text-secondary hover:text-text font-medium">
              <Icons.ChevronLeft className="w-4 h-4" />
              <span>Back to Sign In</span>
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
};
export default ForgotPasswordPage;

