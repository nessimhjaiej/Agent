import { useEffect, useRef, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { RxHamburgerMenu } from 'react-icons/rx';
import {
  Sun,
  Moon,
  LogOut,
  LogIn,
  X,
  KeyRound,
  UserCog,
  Bell,
  ShieldAlert,
  LayoutDashboard,
  MessageSquare,
} from 'lucide-react';
import logo from '../assets/logo.png';
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
  const [showMobileMenu, setShowMobileMenu] = useState(false);
  const [securitySummary, setSecuritySummary] = useState({ active_alerts: 0 });
  const [recentAlerts, setRecentAlerts] = useState([]);
  const notificationsRef = useRef(null);
  const mobileMenuRef = useRef(null);
  const isAdmin = user?.user_metadata?.role === 'admin';
  const isAdminPage = location.pathname === '/admin';
  const isSecurityPage = location.pathname === '/security';
  const isChatPage = location.pathname === '/';
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
    if (!showNotifications && !showMobileMenu) return undefined;

    const handlePointerDown = (event) => {
      const clickedNotifications = notificationsRef.current?.contains(event.target);
      const clickedMobileMenu = mobileMenuRef.current?.contains(event.target);

      if (!clickedNotifications) {
        setShowNotifications(false);
      }

      if (!clickedMobileMenu) {
        setShowMobileMenu(false);
      }
    };

    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [showNotifications, showMobileMenu]);

  const handleLogoClick = () => {
    if (location.pathname === '/' && homeRoute === '/') {
      window.location.reload();
      return;
    }

    navigate(homeRoute);
  };

  const getPageTitle = () => {
    return 'Synapse';
  };

  const changePassword = async (nextPassword) => updatePassword(nextPassword);
  const closeTransientMenus = () => {
    setShowNotifications(false);
    setShowMobileMenu(false);
  };

  const handleOpenProfile = () => {
    closeTransientMenus();
    setShowProfileModal(true);
  };

  const handleOpenPassword = () => {
    closeTransientMenus();
    setShowPasswordModal(true);
  };

  const handleMobileSignOut = async () => {
    closeTransientMenus();
    await signOut();
    navigate('/', { replace: true });
  };

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
        className="shrink-0 relative px-0"
        style={{
          background: 'var(--bg-secondary)',
          borderBottom: '1px solid var(--border-color)',
        }}
      >
        <div
          className="w-full min-h-16 flex items-center gap-3 sm:gap-4 relative py-2"
          style={{ paddingInline: 'clamp(24px, 8vw, 320px)' }}
        >
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

          <div className="flex items-center gap-3 sm:gap-4 min-w-0 flex-1">
            <motion.div
              className="w-14 h-14 rounded-xl flex items-center justify-center shrink-0 cursor-pointer"
              style={{
                background: 'transparent',
                boxShadow: 'none',
              }}
              whileHover={{ scale: 1.05 }}
              onClick={handleLogoClick}
            >
              <img src={logo} alt="Agentic RAG logo" className="w-10 h-10 object-contain" />
            </motion.div>
            <div className="min-w-0">
              <h1
                className="text-sm sm:text-base font-semibold font-display tracking-tight truncate"
                style={{ color: 'var(--text-primary)' }}
              >
                {getPageTitle()}
              </h1>
            </div>
          </div>

          <div className="flex items-center gap-1.5 sm:gap-2 ml-auto min-w-0">
            <motion.button
              id="theme-toggle"
              onClick={toggleTheme}
              className="hidden lg:inline-flex p-2.5 sm:p-3 rounded-xl transition-colors hover:bg-primary-500/10 shrink-0"
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

            <div className="relative lg:hidden" ref={mobileMenuRef}>
              <motion.button
                type="button"
                onClick={() => {
                  setShowMobileMenu((current) => !current);
                  setShowNotifications(false);
                }}
                className="inline-flex items-center justify-center w-12 h-11 rounded-xl transition-colors hover:bg-primary-500/10 shrink-0"
                style={{ color: 'var(--text-secondary)' }}
                title="Open navigation menu"
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
              >
                <AnimatePresence mode="wait" initial={false}>
                  {showMobileMenu ? (
                    <motion.span
                      key="mobile-close"
                      initial={{ opacity: 0, rotate: -90, scale: 0.7 }}
                      animate={{ opacity: 1, rotate: 0, scale: 1 }}
                      exit={{ opacity: 0, rotate: 90, scale: 0.7 }}
                      transition={{ duration: 0.18, ease: 'easeOut' }}
                      className="inline-flex items-center justify-center"
                      style={{ color: '#ef4444' }}
                    >
                      <X size={23} strokeWidth={2.4} />
                    </motion.span>
                  ) : (
                    <motion.span
                      key="mobile-burger"
                      initial={{ opacity: 0, rotate: 90, scale: 0.7 }}
                      animate={{ opacity: 1, rotate: 0, scale: 1 }}
                      exit={{ opacity: 0, rotate: -90, scale: 0.7 }}
                      transition={{ duration: 0.18, ease: 'easeOut' }}
                      className="inline-flex items-center justify-center"
                    >
                      <RxHamburgerMenu size={24} className="block shrink-0" />
                    </motion.span>
                  )}
                </AnimatePresence>
              </motion.button>

            </div>

            {user ? (
              <div className="hidden lg:flex items-center gap-1.5 sm:gap-3 min-w-0">
                {isAdmin && (
                  <motion.button
                    type="button"
                    onClick={() => {
                      closeTransientMenus();
                      navigate(isChatPage ? '/admin' : '/');
                    }}
                    className="relative p-2.5 rounded-xl transition-colors hover:bg-primary-500/10"
                    style={{ color: isChatPage ? 'var(--color-primary-400)' : 'var(--text-secondary)' }}
                    title={isChatPage ? 'Back to admin dashboard' : 'Open user chat'}
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                  >
                    {isChatPage ? <LayoutDashboard size={18} /> : <MessageSquare size={18} />}
                  </motion.button>
                )}

                {isAdmin && (
                  <motion.button
                    type="button"
                    onClick={() => {
                      closeTransientMenus();
                      navigate(isSecurityPage ? '/admin' : '/security');
                    }}
                    className="relative p-2.5 rounded-xl transition-colors hover:bg-primary-500/10"
                    style={{ color: 'var(--text-secondary)' }}
                    title={isSecurityPage ? 'Open admin dashboard' : 'Open security dashboard'}
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                  >
                    {isSecurityPage ? <LayoutDashboard size={18} /> : <ShieldAlert size={18} />}
                  </motion.button>
                )}

                {isAdmin && (
                  <div className="relative" ref={notificationsRef}>
                    <motion.button
                      onClick={() => setShowNotifications((current) => !current)}
                      className="relative p-2.5 rounded-xl transition-colors hover:bg-primary-500/10"
                      style={{ color: 'var(--text-secondary)' }}
                      title="Security alerts"
                      initial={{ y: 0 }}
                      animate={{ y: 4 }}
                      whileHover={{ scale: 1.05 }}
                      whileTap={{ scale: 0.95 }}
                    >
                      <Bell size={18} />
                      {securitySummary.active_alerts > 0 && (
                        <span
                          className="absolute -top-2.5 -right-1.5 min-w-4 h-4 px-1 rounded-full text-[9px] font-semibold flex items-center justify-center"
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
                          className="absolute right-0 mt-3 rounded-2xl overflow-hidden z-30 flex flex-col"
                          style={{
                            width: 'min(560px, calc(100vw - 24px))',
                            maxHeight: 'min(70vh, 640px)',
                            background: 'var(--bg-secondary)',
                            border: '1px solid var(--border-color)',
                            boxShadow: '0 20px 60px rgba(2, 6, 23, 0.28)',
                          }}
                        >
                          <div
                            className="grid grid-cols-[8px_52px_minmax(0,1.05fr)_minmax(0,1.7fr)_148px] gap-x-4 px-6 py-4.5 items-center min-h-[68px]"
                            style={{ borderBottom: 'none' }}
                          >
                            <div className="min-w-0 col-start-2 col-span-3">
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
                                closeTransientMenus();
                                navigate('/security');
                              }}
                              className="text-xs font-medium justify-self-center"
                              style={{ color: 'var(--color-primary-400)' }}
                            >
                              Open dashboard
                            </button>
                          </div>

                          <div
                            className="notification-scroll-area flex-1 overflow-y-auto px-6 py-4 overscroll-contain"
                            style={{
                              WebkitOverflowScrolling: 'touch',
                              touchAction: 'pan-y',
                            }}
                          >
                            {recentAlerts.length > 0 ? (
                              <div className="space-y-1">
                                <div
                                  className="grid grid-cols-[8px_52px_minmax(0,1.05fr)_minmax(0,1.7fr)_148px] gap-x-4 px-2 pb-3 text-[11px] uppercase tracking-[0.14em]"
                                  style={{ color: 'var(--text-muted)' }}
                                >
                                  <div />
                                  <div className="w-9 shrink-0" />
                                  <div className="pl-2">Alert</div>
                                  <div>Details</div>
                                  <div className="flex items-center justify-center text-center">Status</div>
                                </div>
                                {recentAlerts.map((alert) => {
                                  const severity = severityStyles[alert.severity] || severityStyles.info;
                                  return (
                                    <button
                                      key={alert.id}
                                      type="button"
                                      onClick={() => {
                                        closeTransientMenus();
                                        navigate('/security');
                                      }}
                                      className="w-full text-left px-2 py-3 rounded-xl transition-colors hover:bg-primary-500/5"
                                      style={{ background: 'transparent' }}
                                    >
                                      <div className="grid grid-cols-[8px_52px_minmax(0,1.05fr)_minmax(0,1.7fr)_148px] gap-x-4 items-stretch">
                                        <div />
                                        <div
                                          className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
                                          style={{ background: severity.background }}
                                        >
                                          <ShieldAlert size={16} style={{ color: severity.color }} />
                                        </div>
                                        <div className="min-w-0 pl-2">
                                          <p className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>
                                            {alert.title}
                                          </p>
                                          <p className="text-[11px] mt-1 truncate" style={{ color: 'var(--text-muted)' }}>
                                            {alert.source_service}
                                          </p>
                                        </div>
                                        <div className="min-w-0">
                                          <p className="text-xs leading-5 line-clamp-2" style={{ color: 'var(--text-secondary)' }}>
                                            {alert.message}
                                          </p>
                                        </div>
                                        <div className="min-w-[148px] flex flex-col items-center justify-center text-center">
                                          <span
                                            className="inline-flex min-w-[92px] min-h-[34px] items-center justify-center text-[10px] uppercase px-4 py-1.5 rounded-full"
                                            style={{
                                              color: severity.color,
                                              background: severity.background,
                                            }}
                                          >
                                            {alert.severity}
                                          </span>
                                          <p className="text-[11px] mt-2 whitespace-nowrap" style={{ color: 'var(--text-muted)' }}>
                                            {formatAlertTime(alert.last_seen_at)}
                                          </p>
                                          <p className="text-[11px] mt-1 whitespace-nowrap" style={{ color: 'var(--text-muted)' }}>
                                            {alert.count} occurrence{alert.count > 1 ? 's' : ''}
                                          </p>
                                        </div>
                                      </div>
                                    </button>
                                  );
                                })}
                              </div>
                            ) : (
                              <div
                                className="px-6 py-10 text-center"
                                style={{ background: 'transparent' }}
                              >
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

                <div className="hidden lg:block text-right min-w-0 max-w-[220px]">
                  <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                    {user.user_metadata?.username || user.user_metadata?.full_name || user.email?.split('@')[0]}
                  </p>
                  <p className="text-xs truncate" style={{ color: 'var(--text-muted)' }}>
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
                  onClick={handleOpenProfile}
                  className="p-2 rounded-xl transition-colors hover:bg-primary-500/10 shrink-0"
                  style={{ color: 'var(--text-secondary)' }}
                  title="Edit profile"
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                >
                  <UserCog size={17} />
                </motion.button>
                <motion.button
                  onClick={handleOpenPassword}
                  className="p-2 rounded-xl transition-colors hover:bg-primary-500/10 shrink-0 hidden lg:inline-flex"
                  style={{ color: 'var(--text-secondary)' }}
                  title="Change password"
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                >
                  <KeyRound size={17} />
                </motion.button>
                <motion.button
                  id="sign-out-btn"
                  onClick={handleMobileSignOut}
                  className="p-2 rounded-xl transition-colors hover:bg-danger/10 text-danger shrink-0"
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
                className="hidden lg:flex items-center gap-2 rounded-xl text-sm font-medium transition-all shrink-0"
                style={{
                  background: 'linear-gradient(135deg, #7c3aed, #06b6d4)',
                  color: 'white',
                  boxShadow: '0 0 20px rgba(139,92,246,0.3)',
                  paddingLeft: '16px',
                  paddingRight: '16px',
                  paddingTop: '10px',
                  paddingBottom: '10px',
                  minHeight: '44px',
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

      <AnimatePresence>
        {showMobileMenu && (
          <motion.div
            ref={mobileMenuRef}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 12 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            className="fixed inset-0 z-40 lg:hidden flex flex-col overflow-hidden"
            style={{
              background: 'var(--bg-primary)',
            }}
          >
            <div className="h-full px-4 sm:px-6 md:px-8 py-4 sm:py-5 relative">
              <div className="absolute top-5 sm:top-6 md:top-7 right-5 sm:right-6 md:right-8 z-10">
                <motion.button
                  type="button"
                  onClick={closeTransientMenus}
                  className="inline-flex items-center justify-center rounded-2xl w-12 h-12 md:w-13 md:h-13"
                  style={{
                    border: '1px solid rgba(239,68,68,0.18)',
                    color: '#ef4444',
                    background: 'rgba(239,68,68,0.08)',
                  }}
                  aria-label="Close mobile menu"
                  initial={{ opacity: 0, scale: 0.82, rotate: -18 }}
                  animate={{ opacity: 1, scale: 1, rotate: 0 }}
                  exit={{ opacity: 0, scale: 0.82, rotate: 18 }}
                  transition={{ duration: 0.2, ease: 'easeOut' }}
                >
                  <X size={20} />
                </motion.button>
              </div>
              <div className="h-[calc(100%-3.5rem)] w-full mx-auto relative">
                {user ? (
                  <div
                    className="absolute left-1/2 top-[24%] md:top-[22%] -translate-x-1/2 -translate-y-1/2 flex flex-col items-center text-center gap-2 sm:gap-2.5"
                    style={{ width: 'clamp(260px, 70vw, 420px)' }}
                  >
                    <div className="relative">
                      {user.user_metadata?.profile_picture ? (
                        <img
                          src={user.user_metadata.profile_picture}
                          alt="Profile"
                          className="w-20 h-20 md:w-24 md:h-24 rounded-full object-cover"
                          style={{ boxShadow: '0 0 18px rgba(139,92,246,0.22)' }}
                        />
                      ) : (
                          <div
                          className="w-20 h-20 md:w-24 md:h-24 rounded-full flex items-center justify-center text-2xl md:text-3xl font-bold text-white"
                          style={{
                            background: 'linear-gradient(135deg, #7c3aed, #06b6d4)',
                            boxShadow: '0 0 18px rgba(139,92,246,0.22)',
                          }}
                        >
                          {(user.user_metadata?.username || user.user_metadata?.full_name || user.email || 'U')[0].toUpperCase()}
                        </div>
                      )}
                      <div
                        className="absolute bottom-1 right-1 w-3.5 h-3.5 rounded-full border-2"
                        style={{
                          background: 'var(--color-success)',
                          borderColor: 'var(--bg-primary)',
                        }}
                      />
                    </div>
                    <div className="w-full">
                      <p className="text-base md:text-lg font-semibold text-wrap-anywhere" style={{ color: 'var(--text-primary)' }}>
                        {user.user_metadata?.username || user.user_metadata?.full_name || user.email?.split('@')[0]}
                      </p>
                      <p className="text-sm md:text-base mt-1 text-wrap-anywhere" style={{ color: 'var(--text-muted)' }}>
                        {user.email}
                      </p>
                    </div>
                  </div>
                ) : null}

                <div className="absolute left-1/2 top-[58%] md:top-[56%] -translate-x-1/2 -translate-y-1/2 w-full flex flex-col items-center gap-3 md:gap-4">
                  <div
                    className="flex flex-col items-center gap-2.5 md:gap-3"
                    style={{ width: 'clamp(260px, 78vw, 440px)' }}
                  >
                    <button
                      type="button"
                      onClick={() => {
                        closeTransientMenus();
                        toggleTheme();
                      }}
                      className="w-full flex items-center justify-center gap-3 rounded-2xl px-4 md:px-5 py-4 md:py-4.5 text-sm md:text-base text-center"
                      style={{
                        background: 'var(--bg-secondary)',
                        border: '1px solid var(--border-color)',
                        color: 'var(--text-primary)',
                        minHeight: '60px',
                      }}
                    >
                      {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
                      {theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
                    </button>

                    {user ? (
                      <>
                        {isAdmin && (
                          <button
                          type="button"
                          onClick={() => {
                            closeTransientMenus();
                            navigate(isChatPage ? '/admin' : '/');
                          }}
                          className="w-full flex items-center justify-center gap-3 rounded-2xl px-4 md:px-5 py-4 md:py-4.5 text-sm md:text-base text-center"
                          style={{
                            background: 'var(--bg-secondary)',
                            border: '1px solid var(--border-color)',
                            color: 'var(--text-primary)',
                            minHeight: '60px',
                          }}
                          >
                            {isChatPage ? <LayoutDashboard size={18} /> : <MessageSquare size={18} />}
                            <span>{isChatPage ? 'Admin dashboard' : 'User chat'}</span>
                          </button>
                        )}

                        {isAdmin && (
                          <button
                          type="button"
                          onClick={() => {
                            closeTransientMenus();
                            navigate(isSecurityPage ? '/admin' : '/security');
                          }}
                          className="w-full flex items-center justify-center gap-3 rounded-2xl px-4 md:px-5 py-4 md:py-4.5 text-sm md:text-base text-center"
                          style={{
                            background: 'var(--bg-secondary)',
                            border: '1px solid var(--border-color)',
                            color: 'var(--text-primary)',
                            minHeight: '60px',
                          }}
                          >
                            {isSecurityPage ? <LayoutDashboard size={18} /> : <ShieldAlert size={18} />}
                            <span>{isSecurityPage ? 'Admin dashboard' : 'Security dashboard'}</span>
                          </button>
                        )}

                        {isAdmin && (
                          <button
                          type="button"
                          onClick={() => {
                            closeTransientMenus();
                            navigate('/security');
                          }}
                          className="w-full flex items-center justify-center gap-3 rounded-2xl px-4 md:px-5 py-4 md:py-4.5 text-sm md:text-base text-center"
                          style={{
                            background: 'var(--bg-secondary)',
                            border: '1px solid var(--border-color)',
                            color: 'var(--text-primary)',
                            minHeight: '60px',
                          }}
                          >
                            <Bell size={18} />
                            <span>Security alerts</span>
                            <span
                              className="text-[11px] font-semibold px-2.5 py-1 rounded-full"
                              style={{
                                background: securitySummary.active_alerts > 0 ? 'rgba(239,68,68,0.12)' : 'rgba(148,163,184,0.12)',
                                color: securitySummary.active_alerts > 0 ? '#ef4444' : 'var(--text-muted)',
                              }}
                            >
                              {securitySummary.active_alerts || 0}
                            </span>
                          </button>
                        )}

                        <button
                          type="button"
                          onClick={handleOpenProfile}
                          className="w-full flex items-center justify-center gap-3 rounded-2xl px-4 md:px-5 py-4 md:py-4.5 text-sm md:text-base text-center"
                          style={{
                            background: 'var(--bg-secondary)',
                            border: '1px solid var(--border-color)',
                            color: 'var(--text-primary)',
                            minHeight: '60px',
                          }}
                        >
                          <UserCog size={18} />
                          Edit profile
                        </button>

                        <button
                          type="button"
                          onClick={handleOpenPassword}
                          className="w-full flex items-center justify-center gap-3 rounded-2xl px-4 md:px-5 py-4 md:py-4.5 text-sm md:text-base text-center"
                          style={{
                            background: 'var(--bg-secondary)',
                            border: '1px solid var(--border-color)',
                            color: 'var(--text-primary)',
                            minHeight: '60px',
                          }}
                        >
                          <KeyRound size={18} />
                          Change password
                        </button>

                        <button
                          type="button"
                          onClick={handleMobileSignOut}
                          className="w-full flex items-center justify-center gap-3 rounded-2xl px-4 md:px-5 py-4 md:py-4.5 text-sm md:text-base text-center"
                          style={{
                            background: 'rgba(239,68,68,0.08)',
                            border: '1px solid rgba(239,68,68,0.18)',
                            color: '#ef4444',
                            minHeight: '60px',
                          }}
                        >
                          <LogOut size={18} />
                          Sign out
                        </button>
                      </>
                    ) : (
                      <button
                        id="nav-sign-in-mobile"
                        type="button"
                        onClick={() => {
                          closeTransientMenus();
                          navigate('/login');
                        }}
                        className="w-full flex items-center justify-center gap-3 rounded-2xl px-4 md:px-5 py-4 md:py-4.5 text-sm md:text-base text-center"
                        style={{
                          background: 'linear-gradient(135deg, #7c3aed, #06b6d4)',
                          color: 'white',
                          boxShadow: '0 0 20px rgba(139,92,246,0.2)',
                          minHeight: '60px',
                        }}
                      >
                        <LogIn size={18} />
                        Sign In
                      </button>
                    )}
                  </div>
                </div>

                <div
                  className="absolute bottom-2 md:bottom-4 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 pt-1"
                  style={{ width: 'clamp(220px, 60vw, 320px)' }}
                >
                  <div
                    className="w-14 h-14 md:w-16 md:h-16 rounded-2xl flex items-center justify-center"
                    style={{
                      background: 'transparent',
                      boxShadow: 'none',
                    }}
                  >
                    <img src={logo} alt="Agentic RAG logo" className="w-7 h-7 md:w-8 md:h-8 object-contain" />
                  </div>
                  <p className="text-sm md:text-base font-medium" style={{ color: 'var(--text-muted)' }}>
                    Synapse
                  </p>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

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
