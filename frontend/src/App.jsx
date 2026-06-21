import { useState, useEffect } from 'react';
import { Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';
import { useAuth } from './context/AuthContext';
import SplashScreen from './components/SplashScreen';
import Layout from './components/Layout';
import ChatPage from './pages/ChatPage';
import LoginPage from './pages/LoginPage';
import AdminPage from './pages/AdminPage';
import SecurityPage from './pages/SecurityPage';
import NotFoundPage from './pages/NotFoundPage';

function AdminOnlyRoute({ user, userRole, children }) {
  if (!user) return <Navigate to="/" replace />;
  if (userRole !== 'admin') return <Navigate to="/" replace />;
  return children;
}

export default function App() {
  const [showSplash, setShowSplash] = useState(true);
  const { loading, user, userRole, authRefreshKey } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const authenticatedHome = userRole === 'admin' ? '/admin' : '/';

  // Splash screen timer
  useEffect(() => {
    const timer = setTimeout(() => {
      setShowSplash(false);
    }, 2000);
    return () => clearTimeout(timer);
  }, []);

  // Redirect after login based on role
  useEffect(() => {
    if (loading || !user) return;
    const isAdmin = userRole === 'admin';

    // Only force admins to the dashboard right after login. Visiting '/' directly
    // is allowed so an admin can open the user chat from the nav.
    if (isAdmin && location.pathname === '/login') {
      navigate('/admin', { replace: true });
      return;
    }

    if (!isAdmin && (location.pathname === '/admin' || location.pathname === '/security' || location.pathname === '/login')) {
      navigate('/', { replace: true });
    }
  }, [user, loading, location.pathname, userRole, navigate]);

  // Show splash while loading auth or during splash timer
  if (showSplash || loading) {
    return (
      <AnimatePresence mode="wait">
        <SplashScreen key="splash" />
      </AnimatePresence>
    );
  }

  // Login page has its own layout
  if (location.pathname === '/login') {
    if (user) {
      return <Navigate to={authenticatedHome} replace />;
    }

    return (
      <AnimatePresence mode="wait">
        <LoginPage key={`login-${authRefreshKey}`} />
      </AnimatePresence>
    );
  }

  return (
    <Layout key={`layout-${authRefreshKey}`}>
      <AnimatePresence mode="wait">
        <Routes location={location} key={`${location.pathname}-${authRefreshKey}`}>
          <Route path="/" element={<ChatPage />} />
          <Route
            path="/admin"
            element={(
              <AdminOnlyRoute user={user} userRole={userRole}>
                <AdminPage />
              </AdminOnlyRoute>
            )}
          />
          <Route
            path="/security"
            element={(
              <AdminOnlyRoute user={user} userRole={userRole}>
                <SecurityPage />
              </AdminOnlyRoute>
            )}
          />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </AnimatePresence>
    </Layout>
  );
}
