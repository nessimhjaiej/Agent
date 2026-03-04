import { AnimatePresence, motion } from 'framer-motion';
import Navbar from './Navbar';

export default function Layout({ children }) {
  return (
    <div
      className="h-screen w-screen flex flex-col overflow-hidden noise-overlay"
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
        <main className="flex-1 px-4 md:px-10 lg:px-16 xl:px-24 py-2 md:py-4 flex" style={{ minHeight: 0 }}>{children}</main>
      </div>
    </div>
  );
}
