import { motion } from 'framer-motion';

export default function TypingIndicator() {
  return (
    <div className="flex items-center gap-1.5 px-4 py-3">
      {[0, 1, 2].map((i) => (
        <motion.div
          key={i}
          className="w-2 h-2 rounded-full"
          style={{
            background: 'linear-gradient(135deg, #a78bfa, #22d3ee)',
            boxShadow: '0 0 6px rgba(139,92,246,0.4)',
          }}
          animate={{
            y: [0, -8, 0, 3, 0],
            scale: [1, 1.2, 1, 0.9, 1],
            opacity: [0.5, 1, 0.5, 0.7, 0.5],
          }}
          transition={{
            duration: 1.6,
            repeat: Infinity,
            ease: 'easeInOut',
            delay: i * 0.2,
          }}
        />
      ))}
    </div>
  );
}
