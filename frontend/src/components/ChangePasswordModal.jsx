import { useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Lock, Eye, EyeOff, KeyRound, CheckCircle } from 'lucide-react';

export default function ChangePasswordModal({ isOpen, onClose, onSubmit }) {
  const [nextPassword, setNextPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showNextPassword, setShowNextPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const passwordChecks = useMemo(
    () => ({
      minLength: nextPassword.length >= 8,
      hasUpper: /[A-Z]/.test(nextPassword),
      hasLower: /[a-z]/.test(nextPassword),
      hasDigit: /\d/.test(nextPassword),
    }),
    [nextPassword]
  );

  const isStrongPassword = Object.values(passwordChecks).every(Boolean);
  const passwordsMatch = nextPassword.length > 0 && nextPassword === confirmPassword;

  const resetForm = () => {
    setNextPassword('');
    setConfirmPassword('');
    setShowNextPassword(false);
    setShowConfirmPassword(false);
    setLoading(false);
    setError('');
    setSuccess('');
  };

  const closeModal = () => {
    resetForm();
    onClose();
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError('');
    setSuccess('');

    if (!isStrongPassword) {
      setError('Password must include at least 8 chars, upper/lower case, and a number.');
      return;
    }
    if (!passwordsMatch) {
      setError('Password confirmation does not match.');
      return;
    }

    setLoading(true);
    try {
      await onSubmit(nextPassword);
      setSuccess('Password updated successfully.');
      setNextPassword('');
      setConfirmPassword('');
    } catch (submitError) {
      setError(submitError?.message || 'Failed to update password.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            className="fixed inset-0 z-50 bg-black/70 backdrop-blur-md"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={closeModal}
          />

          <motion.div
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 10 }}
            transition={{ type: 'spring', damping: 24, stiffness: 280 }}
          >
            <div
              className="relative w-full max-w-xl rounded-2xl"
              style={{
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border-color)',
                boxShadow: '0 24px 60px rgba(0,0,0,0.4), 0 0 40px rgba(139,92,246,0.16)',
                padding: '32px',
              }}
              onClick={(event) => event.stopPropagation()}
            >
              <button
                type="button"
                onClick={closeModal}
                className="absolute top-4 right-4 p-2.5 rounded-lg transition-colors hover:bg-primary-500/10"
                style={{ color: 'var(--text-muted)' }}
                aria-label="Close change password dialog"
              >
                <X size={18} />
              </button>

              <div className="flex items-center gap-3 mb-8">
                <div
                  className="w-10 h-10 rounded-xl flex items-center justify-center"
                  style={{ background: 'linear-gradient(135deg, #7c3aed, #06b6d4)', color: '#fff' }}
                >
                  <KeyRound size={18} />
                </div>
                <div>
                  <h3 className="text-xl font-semibold font-display" style={{ color: 'var(--text-primary)' }}>
                    Change Password
                  </h3>
                  <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                    Choose a stronger password for your account.
                  </p>
                </div>
              </div>

              <form onSubmit={handleSubmit} className="flex flex-col gap-3" style={{ marginTop: '4px' }}>
                <div
                  className="flex items-center gap-3 rounded-xl transition-all input-glow"
                  style={{
                    border: '1px solid var(--border-color)',
                    background: 'var(--bg-tertiary)',
                    minHeight: '52px',
                    paddingLeft: '16px',
                    paddingRight: '16px',
                  }}
                >
                  <Lock size={16} style={{ color: 'var(--text-muted)' }} />
                  <input
                    id="new-password-input"
                    type={showNextPassword ? 'text' : 'password'}
                    placeholder="New password"
                    value={nextPassword}
                    onChange={(event) => setNextPassword(event.target.value)}
                    className="flex-1 bg-transparent outline-none text-sm"
                    style={{ color: 'var(--text-primary)' }}
                    autoComplete="new-password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowNextPassword((prev) => !prev)}
                    style={{ color: 'var(--text-muted)' }}
                    aria-label={showNextPassword ? 'Hide password' : 'Show password'}
                  >
                    {showNextPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>

                <div
                  className="flex items-center gap-3 rounded-xl transition-all input-glow"
                  style={{
                    border: '1px solid var(--border-color)',
                    background: 'var(--bg-tertiary)',
                    minHeight: '52px',
                    paddingLeft: '16px',
                    paddingRight: '16px',
                  }}
                >
                  <Lock size={16} style={{ color: 'var(--text-muted)' }} />
                  <input
                    id="confirm-password-input"
                    type={showConfirmPassword ? 'text' : 'password'}
                    placeholder="Confirm new password"
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                    className="flex-1 bg-transparent outline-none text-sm"
                    style={{ color: 'var(--text-primary)' }}
                    autoComplete="new-password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowConfirmPassword((prev) => !prev)}
                    style={{ color: 'var(--text-muted)' }}
                    aria-label={showConfirmPassword ? 'Hide password confirmation' : 'Show password confirmation'}
                  >
                    {showConfirmPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>

                <div
                  className="rounded-xl text-xs"
                  style={{
                    border: '1px solid var(--border-color)',
                    background: 'var(--bg-tertiary)',
                    color: 'var(--text-secondary)',
                    padding: '12px 14px',
                  }}
                >
                  <p className="mb-2" style={{ color: 'var(--text-primary)' }}>Password rules</p>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                    <p style={{ color: passwordChecks.minLength ? '#10b981' : 'var(--text-secondary)' }}>At least 8 characters</p>
                    <p style={{ color: passwordChecks.hasUpper ? '#10b981' : 'var(--text-secondary)' }}>One uppercase letter</p>
                    <p style={{ color: passwordChecks.hasLower ? '#10b981' : 'var(--text-secondary)' }}>One lowercase letter</p>
                    <p style={{ color: passwordChecks.hasDigit ? '#10b981' : 'var(--text-secondary)' }}>One number</p>
                  </div>
                </div>

                {error && (
                  <p
                    className="text-sm rounded-lg"
                    style={{
                      background: 'rgba(239,68,68,0.08)',
                      color: '#ef4444',
                      border: '1px solid rgba(239,68,68,0.2)',
                      padding: '10px 12px',
                    }}
                  >
                    {error}
                  </p>
                )}

                {success && (
                  <p
                    className="text-sm rounded-lg flex items-center gap-2"
                    style={{
                      background: 'rgba(16,185,129,0.1)',
                      color: '#10b981',
                      border: '1px solid rgba(16,185,129,0.2)',
                      padding: '10px 12px',
                    }}
                  >
                    <CheckCircle size={14} />
                    {success}
                  </p>
                )}

                <div className="flex items-center justify-end gap-4 mt-1">
                  <button
                    type="button"
                    onClick={closeModal}
                    className="px-4 rounded-xl text-sm font-medium transition-colors"
                    style={{
                      color: 'var(--text-secondary)',
                      border: '1px solid var(--border-color)',
                      minHeight: '44px',
                    }}
                  >
                    Cancel
                  </button>
                  <motion.button
                    id="change-password-submit"
                    type="submit"
                    disabled={loading}
                    className="rounded-xl text-sm font-semibold text-white disabled:opacity-60"
                    style={{
                      background: 'linear-gradient(135deg, #7c3aed, #06b6d4)',
                      boxShadow: '0 0 20px rgba(139,92,246,0.3)',
                      minHeight: '44px',
                      minWidth: '200px',
                      paddingLeft: '30px',
                      paddingRight: '30px',
                    }}
                    whileHover={{ scale: 1.01 }}
                    whileTap={{ scale: 0.98 }}
                  >
                    {loading ? 'Updating...' : 'Update Password'}
                  </motion.button>
                </div>
              </form>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
