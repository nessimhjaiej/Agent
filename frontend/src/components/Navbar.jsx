import { useEffect, useRef, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Sun,
  Moon,
  LogOut,
  LogIn,
  Scale,
  KeyRound,
  UserCog,
  Bell,
  ShieldAlert,
} from 'lucide-react';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import { getSecurityAlertsSummary, listSecurityAlerts } from '../config/api';
import ChangePasswordModal from './ChangePasswordModal';
import ProfileModal from './ProfileModal';

function formatAlertTime(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat([], {
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

const severityStyles = {
  critical: {
    color: '#ef4444',
    background: 'rgba(239,68,68,0.12)',
    border: 'rgba(239,68,68,0.22)',
  },
  warning: {
    color: '#f59e0b',
    background: 'rgba(245,158,11,0.12)',
    border: 'rgba(245,158,11,0.22)',
  },
  info: {
    color: '#3b82f6',
    background: 'rgba(59,130,246,0.12)',
    border: 'rgba(59,130,246,0.22)',
  },
};

export default function Navbar() {
  const { theme, toggleTheme } = useTheme();
  const { user, signOut, updatePassword, updateProfile, requireInviteOnboarding } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [showPasswordModal, setShowPasswordModal] = useState(false);
  const [showProfileModal, setShowProfileModal] = useState(false);
  const [showNotifications, setShowNotifications] = useState(false);
  const [securitySummary, setSecuritySummary] = useState({ active_alerts: 0 });
  const [recentAlerts, setRecentAlerts] = useState([]);
  const notificationsRef = useRef(null);
  const isAdmin = user?.user_metadata?.role === 'admin';
  const homeRoute = isAdmin ? '/admin' : '/';

  useEffect(() => {
    if (!isAdmin) return undefined;

    let cancelled = false;

    const loadNotifications = async () => {
      try {
        const [summary, alertsResponse] = await Promise.all([
          getSecurityAlertsSummary(),
          listSecurityAlerts(false),
        ]);
        if (cancelled) return;
        setSecuritySummary(summary);
        setRecentAlerts((alertsResponse.alerts || []).slice(0, 5));
      } catch {
        if (!cancelled) {
          setSecuritySummary({ active_alerts: 0 });
          setRecentAlerts([]);
        }
      }
    };

    loadNotifications();
    const intervalId = window.setInterval(loadNotifications, 10000);
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        loadNotifications();
      }
    };
    document.addEventListener('visibilitychange', onVisibilityChange);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, [isAdmin]);

  useEffect(() => {
    if (!showNotifications) return undefined;

    const handlePointerDown = (event) => {
      if (!notificationsRef.current?.contains(event.target)) {
        setShowNotifications(false);
      }
    };

    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [showNotifications]);

  const handleLogoClick = () => {
    if (location.pathname === '/' && homeRoute === '/') {
      window.location.reload();
      return;
    }

    navigate(homeRoute);
  };

  const getPageTitle = () => {
    switch (location.pathname) {
      case '/': return 'RAG Chat';
      case '/admin': return 'Admin Panel';
      case '/security': return 'Security Dashboard';
      case '/login': return 'Sign In';
      default: return 'Agentic RAG';
    }
  };

  const changePassword = async (nextPassword) => updatePassword(nextPassword);
  const saveProfile = async ({
    username,
    phoneNumber,
    profilePictureFile,
    removeProfilePicture,
    newPassword,
  }) =>
    updateProfile({
      username,
      phoneNumber,
      profilePictureFile,
      removeProfilePicture,
      newPassword: requireInviteOnboarding ? newPassword : '',
      completeInviteOnboarding: requireInviteOnboarding,
    });

  return (
    <>
      <header
        className="h-16 shrink-0 relative px-3 md:px-6"
        style={{
          background: 'var(--bg-secondary)',
          borderBottom: '1px solid var(--border-color)',
        }}
      >
        <div className="w-full h-full flex items-center relative">
          <motion.div
            className="absolute bottom-0 left-0 right-0 h-px"
            style={{
              background: 'linear-gradient(90deg, transparent, rgba(139,92,246,0.3), rgba(6,182,212,0.2), transparent)',
            }}
            animate={{
              opacity: [0.3, 0.6, 0.3],
            }}
            transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }}
          />

          <div className="flex items-center gap-4" style={{ marginLeft: '240px' }}>
            <motion.div
              className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0 cursor-pointer"
              style={{
                background: 'linear-gradient(135deg, #7c3aed, #06b6d4)',
                boxShadow: '0 0 20px rgba(139,92,246,0.3)',
              }}
              whileHover={{ scale: 1.05, boxShadow: '0 0 30px rgba(139,92,246,0.5)' }}
              onClick={handleLogoClick}
            >
              <Scale className="w-4.5 h-4.5 text-white" />
            </motion.div>
            <div>
              <h1
                className="text-base font-semibold font-display tracking-tight"
                style={{ color: 'var(--text-primary)' }}
              >
                {getPageTitle()}
              </h1>
            </div>
          </div>

          <div className="flex items-center gap-2" style={{ marginLeft: 'auto', marginRight: '240px' }}>
            <motion.button
              id="theme-toggle"
              onClick={toggleTheme}
              className="p-3.5 rounded-xl transition-colors hover:bg-primary-500/10"
              style={{ color: 'var(--text-secondary)' }}
              title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              <AnimatePresence mode="wait">
                {theme === 'dark' ? (
                  <motion.div
                    key="sun"
                    initial={{ rotate: -90, opacity: 0 }}
                    animate={{ rotate: 0, opacity: 1 }}
                    exit={{ rotate: 90, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                  >
                    <Sun size={18} />
                  </motion.div>
                ) : (
                  <motion.div
                    key="moon"
                    initial={{ rotate: 90, opacity: 0 }}
                    animate={{ rotate: 0, opacity: 1 }}
                    exit={{ rotate: -90, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                  >
                    <Moon size={18} />
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.button>

            {user ? (
              <div className="flex items-center gap-3">
                {isAdmin && (
                  <div className="relative" ref={notificationsRef}>
                    <motion.button
                      onClick={() => setShowNotifications((current) => !current)}
                      className="relative p-2.5 rounded-xl transition-colors hover:bg-primary-500/10"
                      style={{ color: 'var(--text-secondary)' }}
                      title="Security alerts"
                      whileHover={{ scale: 1.05 }}
                      whileTap={{ scale: 0.95 }}
                    >
                      <Bell size={18} />
                      {securitySummary.active_alerts > 0 && (
                        <span
                          className="absolute -top-1 -right-1 min-w-5 h-5 px-1 rounded-full text-[10px] font-semibold flex items-center justify-center"
                          style={{
                            background: '#ef4444',
                            color: 'white',
                            boxShadow: '0 0 14px rgba(239,68,68,0.35)',
                          }}
                        >
                          {securitySummary.active_alerts > 99 ? '99+' : securitySummary.active_alerts}
                        </span>
                      )}
                    </motion.button>

                    <AnimatePresence>
                      {showNotifications && (
                        <motion.div
                          initial={{ opacity: 0, y: 8, scale: 0.98 }}
                          animate={{ opacity: 1, y: 0, scale: 1 }}
                          exit={{ opacity: 0, y: 8, scale: 0.98 }}
                          transition={{ duration: 0.18 }}
                          className="absolute right-0 mt-3 w-[360px] rounded-2xl overflow-hidden z-30"
                          style={{
                            background: 'var(--bg-secondary)',
                            border: '1px solid var(--border-color)',
                            boxShadow: '0 20px 60px rgba(2, 6, 23, 0.28)',
                          }}
                        >
                          <div
                            className="px-4 py-3 flex items-center justify-between"
                            style={{ borderBottom: '1px solid var(--border-color)' }}
                          >
                            <div>
                              <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                                Security alerts
                              </p>
                              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                                {securitySummary.active_alerts || 0} active alert{securitySummary.active_alerts === 1 ? '' : 's'}
                              </p>
                            </div>
                            <button
                              type="button"
                              onClick={() => {
                                setShowNotifications(false);
                                navigate('/security');
                              }}
                              className="text-xs font-medium"
                              style={{ color: 'var(--color-primary-400)' }}
                            >
                              Open dashboard
                            </button>
                          </div>

                          <div className="max-h-[340px] overflow-y-auto">
                            {recentAlerts.length > 0 ? recentAlerts.map((alert) => {
                              const severity = severityStyles[alert.severity] || severityStyles.info;
                              return (
                                <button
                                  key={alert.id}
                                  type="button"
                                  onClick={() => {
                                    setShowNotifications(false);
                                    navigate('/security');
                                  }}
                                  className="w-full text-left px-4 py-3 transition-colors"
                                  style={{
                                    borderBottom: '1px solid var(--border-color)',
                                    background: 'transparent',
                                  }}
                                >
                                  <div className="flex items-start gap-3">
                                    <div
                                      className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
                                      style={{ background: severity.background }}
                                    >
                                      <ShieldAlert size={16} style={{ color: severity.color }} />
                                    </div>
                                    <div className="min-w-0 flex-1">
                                      <div className="flex items-center justify-between gap-2">
                                        <p className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>
                                          {alert.title}
                                        </p>
                                        <span
                                          className="text-[10px] uppercase px-2 py-0.5 rounded-full border"
                                          style={{
                                            color: severity.color,
                                            background: severity.background,
                                            borderColor: severity.border,
                                          }}
                                        >
                                          {alert.severity}
                                        </span>
                                      </div>
                                      <p className="text-xs mt-1 line-clamp-2" style={{ color: 'var(--text-secondary)' }}>
                                        {alert.message}
                                      </p>
                                      <p className="text-[11px] mt-2" style={{ color: 'var(--text-muted)' }}>
                                        {alert.source_service} · {formatAlertTime(alert.last_seen_at)} · {alert.count} occurrence{alert.count > 1 ? 's' : ''}
                                      </p>
                                    </div>
                                  </div>
                                </button>
                              );
                            }) : (
                              <div className="px-4 py-8 text-center">
                                <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                                  No active alerts
                                </p>
                                <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
                                  New security events will appear here.
                                </p>
                              </div>
                            )}
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                )}

                <div className="hidden sm:block text-right">
                  <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                    {user.user_metadata?.username || user.user_metadata?.full_name || user.email?.split('@')[0]}
                  </p>
                  <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                    {user.email}
                  </p>
                </div>
                <div className="relative">
                  {user.user_metadata?.profile_picture ? (
                    <img
                      src={user.user_metadata.profile_picture}
                      alt="Profile"
                      className="w-9 h-9 rounded-full object-cover"
                      style={{ boxShadow: '0 0 12px rgba(139,92,246,0.3)' }}
                    />
                  ) : (
                    <div
                      className="w-9 h-9 rounded-full flex items-center justify-center text-xs font-bold text-white"
                      style={{
                        background: 'linear-gradient(135deg, #7c3aed, #06b6d4)',
                        boxShadow: '0 0 12px rgba(139,92,246,0.3)',
                      }}
                    >
                      {(user.user_metadata?.username || user.user_metadata?.full_name || user.email || 'U')[0].toUpperCase()}
                    </div>
                  )}
                  <div
                    className="absolute bottom-0 right-0 w-2.5 h-2.5 rounded-full border-2"
                    style={{
                      background: 'var(--color-success)',
                      borderColor: 'var(--bg-secondary)',
                    }}
                  />
                </div>
                <motion.button
                  onClick={() => setShowProfileModal(true)}
                  className="p-2 rounded-xl transition-colors hover:bg-primary-500/10"
                  style={{ color: 'var(--text-secondary)' }}
                  title="Edit profile"
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                >
                  <UserCog size={17} />
                </motion.button>
                <motion.button
                  onClick={() => setShowPasswordModal(true)}
                  className="p-2 rounded-xl transition-colors hover:bg-primary-500/10"
                  style={{ color: 'var(--text-secondary)' }}
                  title="Change password"
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                >
                  <KeyRound size={17} />
                </motion.button>
                <motion.button
                  id="sign-out-btn"
                  onClick={async () => {
                    await signOut();
                    navigate('/', { replace: true });
                  }}
                  className="p-2 rounded-xl transition-colors hover:bg-danger/10 text-danger"
                  title="Sign out"
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                >
                  <LogOut size={17} />
                </motion.button>
              </div>
            ) : (
              <motion.button
                id="nav-sign-in"
                onClick={() => navigate('/login')}
                className="flex items-center gap-2 rounded-xl text-sm font-medium transition-all"
                style={{
                  background: 'linear-gradient(135deg, #7c3aed, #06b6d4)',
                  color: 'white',
                  boxShadow: '0 0 20px rgba(139,92,246,0.3)',
                  paddingLeft: '24px',
                  paddingRight: '24px',
                  paddingTop: '10px',
                  paddingBottom: '10px',
                  minHeight: '44px',
                  minWidth: '118px',
                }}
                whileHover={{
                  scale: 1.03,
                  boxShadow: '0 0 30px rgba(139,92,246,0.5)',
                }}
                whileTap={{ scale: 0.97 }}
              >
                <LogIn size={16} />
                <span className="hidden sm:inline">Sign In</span>
              </motion.button>
            )}
          </div>
        </div>
      </header>

      <ChangePasswordModal
        isOpen={showPasswordModal}
        onClose={() => setShowPasswordModal(false)}
        onSubmit={changePassword}
      />
      <ProfileModal
        isOpen={showProfileModal || requireInviteOnboarding}
        onClose={() => setShowProfileModal(false)}
        onSubmit={saveProfile}
        user={user}
        requirePassword={requireInviteOnboarding}
        lockUntilComplete={requireInviteOnboarding}
      />
    </>
  );
}
