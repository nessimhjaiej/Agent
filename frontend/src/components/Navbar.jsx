import { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Sun, Moon, LogOut, LogIn, Scale, KeyRound, UserCog } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import ChangePasswordModal from './ChangePasswordModal';
import ProfileModal from './ProfileModal';

export default function Navbar() {
  const { theme, toggleTheme } = useTheme();
  const { user, signOut, updatePassword, updateProfile, requireInviteOnboarding } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [showPasswordModal, setShowPasswordModal] = useState(false);
  const [showProfileModal, setShowProfileModal] = useState(false);
  const homeRoute = user?.user_metadata?.role === 'admin' ? '/admin' : '/';

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
        {/* Animated bottom gradient line */}
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

        {/* Left — Logo + Page Title */}
        <div className="flex items-center gap-4" style={{ marginLeft: '240px' }}>
          <motion.div
            className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0 cursor-pointer"
            style={{
              background: 'linear-gradient(135deg, #7c3aed, #06b6d4)',
              boxShadow: '0 0 20px rgba(139,92,246,0.3)',
            }}
            whileHover={{ scale: 1.05, boxShadow: '0 0 30px rgba(139,92,246,0.5)' }}
            onClick={() => navigate(homeRoute)}
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
        {/* Right */}
        <div className="flex items-center gap-2" style={{ marginLeft: 'auto', marginRight: '240px' }}>
          {/* Theme toggle */}
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

          {/* Auth area */}
          {user ? (
            <div className="flex items-center gap-3">
              <div className="hidden sm:block text-right">
                <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                  {user.user_metadata?.username || user.user_metadata?.full_name || user.email?.split('@')[0]}
                </p>
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                  {user.email}
                </p>
              </div>
              {/* Avatar with gradient ring */}
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
                {/* Online dot */}
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
