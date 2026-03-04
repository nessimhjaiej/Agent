import { NavLink } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  MessageSquare,
  ShieldCheck,
  FolderCog,
  ChevronLeft,
  ChevronRight,
  Scale,
} from 'lucide-react';

const navItems = [
  { path: '/', label: 'Chat', icon: MessageSquare },
  { path: '/admin', label: 'Admin Panel', icon: FolderCog },
  { path: '/security', label: 'Security', icon: ShieldCheck },
];

export default function Sidebar({ collapsed, onToggle }) {
  return (
    <motion.aside
      className="hidden md:flex flex-col h-full shrink-0 relative"
      style={{
        background: 'var(--bg-secondary)',
        borderRight: '1px solid var(--border-color)',
      }}
      animate={{ width: collapsed ? 72 : 250 }}
      transition={{ duration: 0.3, ease: [0.25, 0.46, 0.45, 0.94] }}
    >
      {/* Logo Area */}
      <div
        className="flex items-center gap-3 px-5 h-16 border-b"
        style={{ borderColor: 'var(--border-color)' }}
      >
        <motion.div
          className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
          style={{
            background: 'linear-gradient(135deg, #7c3aed, #06b6d4)',
            boxShadow: '0 0 20px rgba(139,92,246,0.3)',
          }}
          whileHover={{ scale: 1.05, boxShadow: '0 0 30px rgba(139,92,246,0.5)' }}
        >
          <Scale className="w-4.5 h-4.5 text-white" />
        </motion.div>
        <AnimatePresence>
          {!collapsed && (
            <motion.span
              className="text-sm font-bold whitespace-nowrap overflow-hidden font-display tracking-tight"
              style={{ color: 'var(--text-primary)' }}
              initial={{ opacity: 0, width: 0 }}
              animate={{ opacity: 1, width: 'auto' }}
              exit={{ opacity: 0, width: 0 }}
              transition={{ duration: 0.25 }}
            >
              Agentic <span className="gradient-text">RAG</span>
            </motion.span>
          )}
        </AnimatePresence>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-5 px-3 space-y-1">
        {navItems.map(({ path, label, icon: Icon }) => (
          <NavLink
            key={path}
            to={path}
            className={({ isActive }) =>
              `group relative flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 ${
                isActive
                  ? ''
                  : 'hover:bg-primary-500/5'
              }`
            }
            style={({ isActive }) => ({
              color: isActive ? 'var(--color-primary-400)' : 'var(--text-secondary)',
              background: isActive ? 'rgba(139,92,246,0.08)' : undefined,
            })}
          >
            {({ isActive }) => (
              <>
                {/* Active indicator bar */}
                {isActive && (
                  <motion.div
                    className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 rounded-r-full"
                    style={{
                      background: 'linear-gradient(180deg, #a78bfa, #06b6d4)',
                      boxShadow: '0 0 8px rgba(139,92,246,0.4)',
                    }}
                    layoutId="sidebar-indicator"
                    transition={{ type: 'spring', stiffness: 300, damping: 25 }}
                  />
                )}
                <motion.div
                  whileHover={{ scale: 1.1 }}
                  transition={{ duration: 0.2 }}
                >
                  <Icon size={18} className="shrink-0" />
                </motion.div>
                <AnimatePresence>
                  {!collapsed && (
                    <motion.span
                      className="whitespace-nowrap overflow-hidden"
                      initial={{ opacity: 0, width: 0 }}
                      animate={{ opacity: 1, width: 'auto' }}
                      exit={{ opacity: 0, width: 0 }}
                      transition={{ duration: 0.25 }}
                    >
                      {label}
                    </motion.span>
                  )}
                </AnimatePresence>
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Bottom gradient fade */}
      <div
        className="h-20 pointer-events-none"
        style={{
          background: `linear-gradient(to top, var(--bg-secondary), transparent)`,
        }}
      />

      {/* Collapse toggle */}
      <motion.button
        onClick={onToggle}
        className="absolute -right-3.5 top-20 w-7 h-7 rounded-full flex items-center justify-center shadow-md z-10"
        style={{
          background: 'var(--bg-secondary)',
          border: '1px solid var(--border-color)',
          color: 'var(--text-muted)',
        }}
        whileHover={{
          scale: 1.15,
          boxShadow: '0 0 15px rgba(139,92,246,0.3)',
          borderColor: 'rgba(139,92,246,0.3)',
        }}
        transition={{ duration: 0.2 }}
      >
        {collapsed ? <ChevronRight size={12} /> : <ChevronLeft size={12} />}
      </motion.button>
    </motion.aside>
  );
}
