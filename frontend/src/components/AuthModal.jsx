import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Mail, Lock, Github, Eye, EyeOff, CheckCircle, ArrowRight } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export default function AuthModal({ isOpen, onClose }) {
  const [mode, setMode] = useState('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [emailSent, setEmailSent] = useState(false);
  const { signIn, signUp, signInWithOAuth } = useAuth();

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

  const handleOAuth = async (provider) => {
    try {
      await signInWithOAuth(provider);
    } catch (err) {
      setError(err.message || 'OAuth error');
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
              className="relative w-full max-w-md rounded-2xl p-8"
              style={{
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border-color)',
                boxShadow: '0 25px 50px -12px rgba(0,0,0,0.5), 0 0 40px rgba(139,92,246,0.1)',
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
                  <h3 className="text-xl font-semibold font-display mb-2" style={{ color: 'var(--text-primary)' }}>Check your email</h3>
                  <p className="text-sm mb-6" style={{ color: 'var(--text-secondary)' }}>
                    We sent a verification link to <strong>{email}</strong>. Please verify to complete registration.
                  </p>
                  <button onClick={() => { resetForm(); setMode('signin'); }} className="text-sm font-medium gradient-text hover:opacity-80 transition-opacity">
                    Back to Sign In
                  </button>
                </motion.div>
              ) : (
                <>
                  {/* Header */}
                  <div className="text-center mb-6">
                    <h2 className="text-2xl font-bold font-display" style={{ color: 'var(--text-primary)' }}>
                      {mode === 'signin' ? 'Welcome back' : 'Create account'}
                    </h2>
                    <p className="text-sm mt-1" style={{ color: 'var(--text-secondary)' }}>
                      {mode === 'signin' ? 'Sign in to continue your conversation' : 'Sign up to start querying legal content'}
                    </p>
                  </div>

                  {/* OAuth */}
                  <div className="flex gap-3 mb-6">
                    {[
                      { provider: 'google', label: 'Google', icon: (
                        <svg className="w-5 h-5" viewBox="0 0 24 24">
                          <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4" />
                          <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
                          <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
                          <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
                        </svg>
                      )},
                      { provider: 'github', label: 'GitHub', icon: <Github size={18} /> },
                    ].map(({ provider, label, icon }) => (
                      <motion.button
                        key={provider}
                        onClick={() => handleOAuth(provider)}
                        className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all"
                        style={{ border: '1px solid var(--border-color)', color: 'var(--text-primary)', background: 'var(--bg-tertiary)' }}
                        whileHover={{ borderColor: 'rgba(139,92,246,0.3)', boxShadow: '0 0 15px rgba(139,92,246,0.1)' }}
                        whileTap={{ scale: 0.98 }}
                      >
                        {icon}
                        {label}
                      </motion.button>
                    ))}
                  </div>

                  {/* Divider */}
                  <div className="flex items-center gap-3 mb-6">
                    <div className="flex-1 h-px" style={{ background: 'var(--border-color)' }} />
                    <span className="text-xs font-medium tracking-wider" style={{ color: 'var(--text-muted)' }}>OR</span>
                    <div className="flex-1 h-px" style={{ background: 'var(--border-color)' }} />
                  </div>

                  {/* Form */}
                  <form onSubmit={handleSubmit} className="space-y-4">
                    <div className="flex items-center gap-3 px-4 py-3 rounded-xl transition-all input-glow" style={{ border: '1px solid var(--border-color)', background: 'var(--bg-tertiary)' }}>
                      <Mail size={16} style={{ color: 'var(--text-muted)' }} />
                      <input id="auth-email" type="email" placeholder="Email address" value={email} onChange={(e) => setEmail(e.target.value)} required className="flex-1 bg-transparent outline-none text-sm" style={{ color: 'var(--text-primary)' }} />
                    </div>

                    <div className="flex items-center gap-3 px-4 py-3 rounded-xl transition-all input-glow" style={{ border: '1px solid var(--border-color)', background: 'var(--bg-tertiary)' }}>
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
                      style={{ background: 'linear-gradient(135deg, #7c3aed, #06b6d4)', boxShadow: '0 0 25px rgba(139,92,246,0.3)' }}
                      whileHover={{ boxShadow: '0 0 40px rgba(139,92,246,0.5)', scale: 1.01 }}
                      whileTap={{ scale: 0.99 }}
                    >
                      {loading ? 'Please wait...' : mode === 'signin' ? 'Sign In' : 'Create Account'}
                      {!loading && <ArrowRight size={16} />}
                    </motion.button>
                  </form>

                  <p className="text-center text-sm mt-6" style={{ color: 'var(--text-secondary)' }}>
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
