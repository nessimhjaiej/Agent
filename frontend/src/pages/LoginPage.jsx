import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Mail, Lock, Eye, EyeOff, Scale, CheckCircle, ArrowRight } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import AnimatedPage from '../components/AnimatedPage';

export default function LoginPage() {
  const [mode, setMode] = useState('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [emailSent, setEmailSent] = useState(false);
  const { signIn, signUp, signInWithOAuth } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      if (mode === 'signin') {
        const data = await signIn(email, password);
        const role = data?.user?.user_metadata?.role;
        navigate(role === 'admin' ? '/admin' : '/');
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

  return (
    <AnimatedPage className="min-h-screen flex">
      {/* Left — Form */}
      <div
        className="flex-1 flex items-center justify-center p-10 md:p-12 relative noise-overlay"
        style={{ background: 'var(--bg-primary)' }}
      >
        {/* Ambient orb */}
        <div
          className="absolute w-[500px] h-[500px] rounded-full animate-aurora pointer-events-none"
          style={{
            background: 'radial-gradient(circle, rgba(139,92,246,0.08), transparent 70%)',
            top: '10%',
            left: '-10%',
          }}
        />

        {emailSent ? (
          <motion.div
            className="w-full max-w-md rounded-2xl p-12 text-center relative"
            style={{
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border-color)',
              boxShadow: '0 25px 50px -12px var(--shadow-color)',
            }}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <motion.div
              className="w-20 h-20 rounded-full flex items-center justify-center mx-auto mb-6"
              style={{
                background: 'rgba(16,185,129,0.1)',
                boxShadow: '0 0 30px rgba(16,185,129,0.2)',
              }}
              animate={{ scale: [1, 1.05, 1] }}
              transition={{ duration: 2, repeat: Infinity }}
            >
              <CheckCircle className="w-10 h-10 text-success" />
            </motion.div>
            <h2 className="text-2xl font-bold font-display mb-3" style={{ color: 'var(--text-primary)' }}>
              Verify your email
            </h2>
            <p className="text-sm mb-6" style={{ color: 'var(--text-secondary)' }}>
              We sent a verification link to <strong>{email}</strong>.
              <br />Please check your inbox to complete registration.
            </p>
            <button
              onClick={() => { setEmailSent(false); setMode('signin'); setEmail(''); setPassword(''); }}
              className="text-sm font-semibold gradient-text hover:opacity-80 transition-opacity"
            >
              ← Back to Sign In
            </button>
          </motion.div>
        ) : (
          <motion.div
            className="w-full max-w-md relative z-10"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
          >
            {/* Logo — Centered above text */}
            <div className="flex flex-col items-center text-center mb-12">
              <motion.div
                className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-5"
                style={{
                  background: 'linear-gradient(135deg, #7c3aed, #06b6d4)',
                  boxShadow: '0 0 40px rgba(139,92,246,0.3), 0 20px 40px -10px rgba(0,0,0,0.3)',
                }}
                whileHover={{ scale: 1.05, rotate: 5 }}
              >
                <Scale className="w-8 h-8 text-white" />
              </motion.div>
              <h1 className="text-3xl md:text-4xl font-bold font-display" style={{ color: 'var(--text-primary)' }}>
                {mode === 'signin' ? 'Welcome back' : 'Get started'}
              </h1>
              <p className="text-sm mt-3" style={{ color: 'var(--text-secondary)' }}>
                {mode === 'signin'
                  ? 'Sign in to your Legal Intelligence account'
                  : 'Create your account to access legal RAG'}
              </p>
            </div>

            {/* Card */}
            <div
              className="rounded-2xl p-10"
              style={{
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border-color)',
                boxShadow: '0 25px 50px -12px var(--shadow-color)',
              }}
            >
              {/* OAuth */}
              <div className="flex gap-4 mb-10">
                {[
                  { provider: 'google', label: 'Google', icon: (
                    <svg className="w-5 h-5" viewBox="0 0 24 24">
                      <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4" />
                      <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
                      <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
                      <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
                    </svg>
                  )},
                ].map(({ provider, label, icon }) => (
                  <motion.button
                    key={provider}
                    onClick={() => handleOAuth(provider)}
                    className="flex-1 flex items-center justify-center gap-2 px-6 py-4.5 rounded-xl text-sm font-medium transition-all"
                    style={{
                      border: '1px solid var(--border-color)',
                      color: 'var(--text-primary)',
                      background: 'var(--bg-tertiary)',
                    }}
                    whileHover={{
                      scale: 1.02,
                      boxShadow: '0 0 20px var(--glow-primary)',
                      borderColor: 'rgba(139,92,246,0.3)',
                    }}
                    whileTap={{ scale: 0.98 }}
                  >
                    {icon}
                    {label}
                  </motion.button>
                ))}
              </div>

              {/* Divider */}
              <div className="flex items-center gap-4 mb-10">
                <div className="flex-1 h-px" style={{ background: 'var(--border-color)' }} />
                <span className="text-xs font-medium tracking-wider" style={{ color: 'var(--text-muted)' }}>OR</span>
                <div className="flex-1 h-px" style={{ background: 'var(--border-color)' }} />
              </div>

              {/* Form */}
              <form onSubmit={handleSubmit} className="space-y-6">
                <div
                  className="flex items-center gap-3 px-5 py-5 rounded-xl transition-all input-glow"
                  style={{
                    border: '1px solid var(--border-color)',
                    background: 'var(--bg-tertiary)',
                  }}
                >
                  <Mail size={16} style={{ color: 'var(--text-muted)' }} />
                  <input
                    id="login-email"
                    type="email"
                    placeholder="Email address"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    autoComplete="email"
                    className="flex-1 bg-transparent outline-none text-sm"
                    style={{ color: 'var(--text-primary)' }}
                  />
                </div>

                <div
                  className="flex items-center gap-3 px-5 py-5 rounded-xl transition-all input-glow"
                  style={{
                    border: '1px solid var(--border-color)',
                    background: 'var(--bg-tertiary)',
                  }}
                >
                  <Lock size={16} style={{ color: 'var(--text-muted)' }} />
                  <input
                    id="login-password"
                    type={showPassword ? 'text' : 'password'}
                    placeholder="Password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    minLength={8}
                    autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
                    className="flex-1 bg-transparent outline-none text-sm"
                    style={{ color: 'var(--text-primary)' }}
                  />
                  <button type="button" onClick={() => setShowPassword(!showPassword)} style={{ color: 'var(--text-muted)' }}>
                    {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>

                {error && (
                  <motion.p
                    className="text-sm text-danger bg-danger/10 rounded-lg px-4 py-3"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                  >
                    {error}
                  </motion.p>
                )}

                <motion.button
                  id="login-submit"
                  type="submit"
                  disabled={loading}
                  className="w-full py-5.5 rounded-xl text-sm font-semibold text-white flex items-center justify-center gap-2 transition-all disabled:opacity-50"
                  style={{
                    background: 'linear-gradient(135deg, #7c3aed, #06b6d4)',
                    boxShadow: '0 0 25px rgba(139,92,246,0.3)',
                  }}
                  whileHover={{
                    boxShadow: '0 0 40px rgba(139,92,246,0.5)',
                    scale: 1.01,
                  }}
                  whileTap={{ scale: 0.99 }}
                >
                  {loading ? 'Please wait...' : mode === 'signin' ? 'Sign In' : 'Create Account'}
                  {!loading && <ArrowRight size={16} />}
                </motion.button>
              </form>

              <p className="text-center text-sm mt-10" style={{ color: 'var(--text-secondary)' }}>
                {mode === 'signin' ? "Don't have an account?" : 'Already have an account?'}{' '}
                <button
                  onClick={() => { setMode(mode === 'signin' ? 'signup' : 'signin'); setError(''); }}
                  className="font-semibold gradient-text hover:opacity-80 transition-opacity"
                >
                  {mode === 'signin' ? 'Sign Up' : 'Sign In'}
                </button>
              </p>
            </div>
          </motion.div>
        )}
      </div>

      {/* Right — Decorative Panel */}
      <div
        className="hidden lg:flex flex-1 items-center justify-center relative overflow-hidden"
        style={{
          background: 'linear-gradient(135deg, #0f0f14 0%, #1a0a2e 50%, #0a1628 100%)',
        }}
      >
        {/* Floating orbs */}
        {[
          { size: 300, x: '10%', y: '15%', color: 'rgba(139,92,246,0.15)', delay: 0 },
          { size: 200, x: '60%', y: '60%', color: 'rgba(6,182,212,0.12)', delay: 2 },
          { size: 250, x: '70%', y: '10%', color: 'rgba(139,92,246,0.08)', delay: 4 },
          { size: 180, x: '20%', y: '70%', color: 'rgba(6,182,212,0.10)', delay: 1 },
          { size: 150, x: '45%', y: '40%', color: 'rgba(167,139,250,0.06)', delay: 3 },
        ].map((orb, i) => (
          <motion.div
            key={i}
            className="absolute rounded-full"
            style={{
              width: orb.size,
              height: orb.size,
              left: orb.x,
              top: orb.y,
              background: `radial-gradient(circle, ${orb.color}, transparent 70%)`,
              filter: 'blur(40px)',
            }}
            animate={{
              x: [0, 30, -20, 0],
              y: [0, -25, 15, 0],
              scale: [1, 1.1, 0.95, 1],
            }}
            transition={{
              duration: 10 + i * 2,
              repeat: Infinity,
              ease: 'easeInOut',
              delay: orb.delay,
            }}
          />
        ))}

        {/* Content — CENTERED */}
        <div className="relative z-10 text-center text-white max-w-sm px-10 flex flex-col items-center">
          <motion.div
            className="w-20 h-20 rounded-2xl flex items-center justify-center mb-8"
            style={{
              background: 'rgba(255,255,255,0.05)',
              border: '1px solid rgba(255,255,255,0.1)',
              backdropFilter: 'blur(20px)',
              boxShadow: '0 0 30px rgba(139,92,246,0.2)',
            }}
            animate={{
              boxShadow: [
                '0 0 30px rgba(139,92,246,0.2)',
                '0 0 50px rgba(139,92,246,0.3)',
                '0 0 30px rgba(139,92,246,0.2)',
              ],
            }}
            transition={{ duration: 3, repeat: Infinity }}
          >
            <Scale className="w-10 h-10" />
          </motion.div>
          <h2 className="text-3xl font-bold font-display mb-4">
            Legal Intelligence
          </h2>
          <p className="text-white/50 text-sm leading-relaxed">
            Query legal and regulatory content with AI-powered Retrieval Augmented Generation.
            Get precise, sourced answers instantly.
          </p>

          {/* Feature pills */}
          <div className="flex flex-wrap justify-center gap-2 mt-10">
            {['AI-Powered', 'Real-time', 'Multi-source', 'Secure'].map((feat, i) => (
              <motion.span
                key={feat}
                className="text-xs px-3 py-1.5 rounded-full"
                style={{
                  background: 'rgba(255,255,255,0.05)',
                  border: '1px solid rgba(255,255,255,0.1)',
                  color: 'rgba(255,255,255,0.6)',
                }}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.5 + i * 0.1 }}
              >
                {feat}
              </motion.span>
            ))}
          </div>
        </div>
      </div>
    </AnimatedPage>
  );
}
