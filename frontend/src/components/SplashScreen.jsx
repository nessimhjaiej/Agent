import { motion } from 'framer-motion';
import { Scale } from 'lucide-react';

export default function SplashScreen() {
  const letters = 'Agentic RAG'.split('');

  return (
    <motion.div
      className="fixed inset-0 z-50 flex flex-col items-center justify-center overflow-hidden"
      style={{ background: 'var(--bg-primary)' }}
      initial={{ opacity: 1 }}
      exit={{ opacity: 0, scale: 0.95, filter: 'blur(10px)' }}
      transition={{ duration: 0.6, ease: 'easeInOut' }}
    >
      {/* Ambient gradient orbs */}
      <div className="absolute inset-0 overflow-hidden">
        <motion.div
          className="absolute w-[600px] h-[600px] rounded-full"
          style={{
            background: 'radial-gradient(circle, rgba(139,92,246,0.2), transparent 70%)',
            top: '-15%',
            left: '-10%',
          }}
          animate={{
            scale: [1, 1.2, 1],
            opacity: [0.3, 0.6, 0.3],
          }}
          transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }}
        />
        <motion.div
          className="absolute w-[500px] h-[500px] rounded-full"
          style={{
            background: 'radial-gradient(circle, rgba(6,182,212,0.15), transparent 70%)',
            bottom: '-10%',
            right: '-10%',
          }}
          animate={{
            scale: [1.1, 0.9, 1.1],
            opacity: [0.2, 0.5, 0.2],
          }}
          transition={{ duration: 5, repeat: Infinity, ease: 'easeInOut' }}
        />
        <motion.div
          className="absolute w-[400px] h-[400px] rounded-full"
          style={{
            background: 'radial-gradient(circle, rgba(139,92,246,0.1), transparent 70%)',
            top: '40%',
            right: '20%',
          }}
          animate={{
            scale: [0.9, 1.15, 0.9],
            x: [0, 30, 0],
            y: [0, -20, 0],
          }}
          transition={{ duration: 6, repeat: Infinity, ease: 'easeInOut' }}
        />
      </div>

      {/* Logo + text container */}
      <motion.div
        className="relative z-10 flex flex-col items-center gap-8"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.4, delay: 0.2 }}
      >
        {/* Logo with glow ring */}
        <motion.div
          className="relative"
          initial={{ scale: 0, rotateY: -90 }}
          animate={{ scale: 1, rotateY: 0 }}
          transition={{ duration: 0.8, delay: 0.3, type: 'spring', damping: 12 }}
        >
          {/* Pulse ring */}
          <motion.div
            className="absolute inset-0 rounded-2xl"
            style={{
              background: 'linear-gradient(135deg, rgba(139,92,246,0.3), rgba(6,182,212,0.3))',
            }}
            animate={{
              scale: [1, 1.4, 1],
              opacity: [0.5, 0, 0.5],
            }}
            transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
          />
          <div
            className="relative w-24 h-24 rounded-2xl flex items-center justify-center shadow-2xl"
            style={{
              background: 'linear-gradient(135deg, #7c3aed, #06b6d4)',
              boxShadow: '0 0 40px rgba(139,92,246,0.4), 0 0 80px rgba(6,182,212,0.2)',
            }}
          >
            <Scale className="w-12 h-12 text-white" />
          </div>
        </motion.div>

        {/* Title with stagger letter animation */}
        <div className="text-center">
          <div className="flex items-center justify-center gap-0.5">
            {letters.map((letter, i) => (
              <motion.span
                key={i}
                className="text-3xl md:text-4xl font-bold font-display"
                style={{
                  color: i >= 8 ? undefined : 'var(--text-primary)',
                  background: i >= 8 ? 'linear-gradient(135deg, #a78bfa, #22d3ee)' : undefined,
                  WebkitBackgroundClip: i >= 8 ? 'text' : undefined,
                  WebkitTextFillColor: i >= 8 ? 'transparent' : undefined,
                }}
                initial={{ opacity: 0, y: 20, filter: 'blur(8px)' }}
                animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
                transition={{
                  duration: 0.4,
                  delay: 0.8 + i * 0.05,
                  ease: 'easeOut',
                }}
              >
                {letter === ' ' ? '\u00A0' : letter}
              </motion.span>
            ))}
          </div>
          <motion.p
            className="text-sm mt-3 tracking-[0.2em] uppercase"
            style={{ color: 'var(--text-muted)' }}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 1.4, duration: 0.5 }}
          >
            Legal Intelligence Platform
          </motion.p>
        </div>

        {/* Loading bar with glow */}
        <motion.div
          className="w-56 h-1 rounded-full overflow-hidden"
          style={{ background: 'var(--border-color)' }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.5 }}
        >
          <motion.div
            className="h-full rounded-full"
            style={{
              background: 'linear-gradient(90deg, #7c3aed, #06b6d4)',
              boxShadow: '0 0 15px rgba(139,92,246,0.5)',
            }}
            initial={{ width: '0%' }}
            animate={{ width: '100%' }}
            transition={{ duration: 1.5, delay: 1.6, ease: [0.25, 0.46, 0.45, 0.94] }}
          />
        </motion.div>
      </motion.div>
    </motion.div>
  );
}
