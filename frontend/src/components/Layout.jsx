import { AnimatePresence, motion } from 'framer-motion';
import { useLocation } from 'react-router-dom';
import Navbar from './Navbar';

export default function Layout({ children }) {
  const location = useLocation();
  const isAdminRoute = location.pathname === '/admin';

  return (
    <div
      className="h-dvh min-h-screen w-full flex flex-col overflow-hidden noise-overlay"
      style={{ background: 'var(--bg-primary)' }}
    >
      {/* Ambient background orbs */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden z-0">
        <div
          className="absolute w-[500px] h-[500px] rounded-full animate-aurora"
          style={{
            background: 'radial-gradient(circle, rgba(139,92,246,0.06), transparent 70%)',
            top: '-100px',
            right: '-100px',
          }}
        />
        <div
          className="absolute w-[400px] h-[400px] rounded-full animate-aurora"
          style={{
            background: 'radial-gradient(circle, rgba(6,182,212,0.04), transparent 70%)',
            bottom: '-80px',
            left: '-80px',
            animationDelay: '3s',
          }}
        />
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 relative z-10" style={{ minHeight: 0 }}>
        <Navbar />
        <main
          className={`flex-1 py-2 md:py-4 flex justify-center ${
            isAdminRoute ? 'px-2 sm:px-3 md:px-4 lg:px-5 xl:px-6' : 'px-3 sm:px-4 md:px-8 lg:px-12 xl:px-16'
          }`}
          style={{ minHeight: 0 }}
        >
          <div className={`w-full min-w-0 flex ${isAdminRoute ? 'max-w-none' : 'max-w-[1680px]'}`}>{children}</div>
        </main>
      </div>
    </div>
  );
}
