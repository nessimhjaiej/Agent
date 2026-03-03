import { useState, useEffect } from 'react';
import { Routes, Route, useLocation, useNavigate } from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';
import { useAuth } from './context/AuthContext';
import SplashScreen from './components/SplashScreen';
import Layout from './components/Layout';
import AnimatedPage from './components/AnimatedPage';
import ChatPage from './pages/ChatPage';
import LoginPage from './pages/LoginPage';
import AdminPage from './pages/AdminPage';
import SecurityPage from './pages/SecurityPage';

export default function App() {
  const [showSplash, setShowSplash] = useState(true);
  const { loading, user, userRole } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  // Splash screen timer
  useEffect(() => {
    const timer = setTimeout(() => {
      setShowSplash(false);
    }, 2000);
    return () => clearTimeout(timer);
  }, []);

  // Redirect after login based on role
  useEffect(() => {
    if (!loading && user && location.pathname === '/login') {
      navigate(userRole === 'admin' ? '/admin' : '/');
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
    return (
      <AnimatePresence mode="wait">
        <LoginPage key="login" />
      </AnimatePresence>
    );
  }

  return (
    <Layout>
      <AnimatePresence mode="wait">
        <Routes location={location} key={location.pathname}>
          <Route path="/" element={<ChatPage />} />
          <Route path="/admin" element={<AdminPage />} />
          <Route path="/security" element={<SecurityPage />} />
          <Route
            path="*"
            element={
              <AnimatedPage className="h-full flex items-center justify-center">
                <div className="text-center">
                  <h1 className="text-6xl font-bold gradient-text mb-4">404</h1>
                  <p style={{ color: 'var(--text-secondary)' }}>Page not found</p>
                </div>
              </AnimatedPage>
            }
          />
        </Routes>
      </AnimatePresence>
    </Layout>
  );
}
