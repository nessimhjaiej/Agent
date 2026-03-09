import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Mail, Lock, Eye, EyeOff, CheckCircle, ArrowRight } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export default function AuthModal({ isOpen, onClose }) {
  const [mode, setMode] = useState('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [emailSent, setEmailSent] = useState(false);
  const { signIn, signUp } = useAuth();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      if (mode === 'signin') {
        await signIn(email, password);
        onClose();
      } else {
        await signUp(email, password);
        setEmailSent(true);
      }
    } catch (err) {
      setError(err.message || 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  const resetForm = () => {
    setEmail(''); setPassword(''); setError(''); setEmailSent(false);
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            className="fixed inset-0 z-50 bg-black/70 backdrop-blur-md"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />

          {/* Modal */}
          <motion.div
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
            initial={{ opacity: 0, scale: 0.9, filter: 'blur(8px)' }}
            animate={{ opacity: 1, scale: 1, filter: 'blur(0px)' }}
            exit={{ opacity: 0, scale: 0.9, filter: 'blur(8px)' }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
          >
            <div
              className="relative w-full max-w-lg rounded-2xl"
              style={{
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border-color)',
                boxShadow: '0 25px 50px -12px rgba(0,0,0,0.5), 0 0 40px rgba(139,92,246,0.1)',
                padding: '44px',
              }}
              onClick={(e) => e.stopPropagation()}
            >
              {/* Close */}
              <motion.button
                onClick={onClose}
                className="absolute top-4 right-4 p-2.5 rounded-lg transition-colors hover:bg-primary-500/10"
                style={{ color: 'var(--text-muted)' }}
                whileHover={{ rotate: 90 }}
                transition={{ duration: 0.2 }}
              >
                <X size={18} />
              </motion.button>

              {emailSent ? (
                <motion.div className="text-center py-6" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
                  <motion.div
                    className="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4"
                    style={{ background: 'rgba(16,185,129,0.1)', boxShadow: '0 0 25px rgba(16,185,129,0.2)' }}
                    animate={{ scale: [1, 1.05, 1] }}
                    transition={{ duration: 2, repeat: Infinity }}
                  >
                    <CheckCircle className="w-8 h-8 text-success" />
                  </motion.div>
                  <h3 className="text-xl font-semibold font-display mb-2" style={{ color: 'var(--text-primary)' }}>Account created</h3>
                  <p className="text-sm mb-6" style={{ color: 'var(--text-secondary)' }}>
                    Your signup request for <strong>{email}</strong> is waiting for admin validation.
                  </p>
                  <button onClick={() => { resetForm(); setMode('signin'); }} className="text-sm font-medium gradient-text hover:opacity-80 transition-opacity">
                    Back to Sign In
                  </button>
                </motion.div>
              ) : (
                <>
                  {/* Header */}
                  <div className="text-center" style={{ marginBottom: '32px' }}>
                    <h2 className="text-2xl font-bold font-display" style={{ color: 'var(--text-primary)' }}>
                      {mode === 'signin' ? 'Welcome back' : 'Create account'}
                    </h2>
                    <p className="text-sm mt-3" style={{ color: 'var(--text-secondary)' }}>
                      {mode === 'signin' ? 'Sign in to continue your conversation' : 'Sign up to start querying legal content'}
                    </p>
                  </div>

                  {/* Form */}
                  <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                    <div className="flex items-center gap-3 px-4 py-4 rounded-xl transition-all input-glow" style={{ border: '1px solid var(--border-color)', background: 'var(--bg-tertiary)', minHeight: '54px', paddingLeft: '16px', paddingRight: '16px', paddingTop: '14px', paddingBottom: '14px' }}>
                      <Mail size={16} style={{ color: 'var(--text-muted)' }} />
                      <input id="auth-email" type="email" placeholder="Email address" value={email} onChange={(e) => setEmail(e.target.value)} required className="flex-1 bg-transparent outline-none text-sm" style={{ color: 'var(--text-primary)' }} />
                    </div>

                    <div className="flex items-center gap-3 px-4 py-4 rounded-xl transition-all input-glow" style={{ border: '1px solid var(--border-color)', background: 'var(--bg-tertiary)', minHeight: '54px', paddingLeft: '16px', paddingRight: '16px', paddingTop: '14px', paddingBottom: '14px' }}>
                      <Lock size={16} style={{ color: 'var(--text-muted)' }} />
                      <input id="auth-password" type={showPassword ? 'text' : 'password'} placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} className="flex-1 bg-transparent outline-none text-sm" style={{ color: 'var(--text-primary)' }} />
                      <button type="button" onClick={() => setShowPassword(!showPassword)} style={{ color: 'var(--text-muted)' }}>
                        {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                      </button>
                    </div>

                    {error && (
                      <motion.p className="text-sm text-danger bg-danger/10 rounded-lg px-3 py-2" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                        {error}
                      </motion.p>
                    )}

                    <motion.button
                      id="auth-submit" type="submit" disabled={loading}
                      className="w-full py-3 rounded-xl text-sm font-semibold text-white flex items-center justify-center gap-2 disabled:opacity-50"
                      style={{ background: 'linear-gradient(135deg, #7c3aed, #06b6d4)', boxShadow: '0 0 25px rgba(139,92,246,0.3)', minHeight: '54px', paddingTop: '14px', paddingBottom: '14px', paddingLeft: '20px', paddingRight: '20px' }}
                      whileHover={{ boxShadow: '0 0 40px rgba(139,92,246,0.5)', scale: 1.01 }}
                      whileTap={{ scale: 0.99 }}
                    >
                      {loading ? 'Please wait...' : mode === 'signin' ? 'Sign In' : 'Create Account'}
                      {!loading && <ArrowRight size={16} />}
                    </motion.button>
                  </form>

                  <p className="text-center text-sm" style={{ color: 'var(--text-secondary)', marginTop: '22px' }}>
                    {mode === 'signin' ? "Don't have an account?" : 'Already have an account?'}{' '}
                    <button onClick={() => { setMode(mode === 'signin' ? 'signup' : 'signin'); setError(''); }} className="font-semibold gradient-text hover:opacity-80 transition-opacity">
                      {mode === 'signin' ? 'Sign Up' : 'Sign In'}
                    </button>
                  </p>
                </>
              )}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
