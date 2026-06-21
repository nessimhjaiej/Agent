import { motion } from 'framer-motion';

// Animated bar waveform shown inside the record button while capturing audio.
export default function VoiceWaveform({ isRecording, samples }) {
  const isActive = isRecording && samples.some((sample) => sample > 0.05);

  return (
    <div className={`voice-waveform ${isActive ? 'is-active' : ''}`} aria-hidden="true">
      {samples.map((sample, index) => {
        const activity = isRecording ? Math.max(0.06, sample) : 0.04;

        return (
          <motion.span
            key={index}
            className="voice-waveform__bar"
            animate={{
              scaleY: Math.min(1, activity),
              opacity: isRecording ? Math.max(0.18, 0.2 + sample * 0.8) : 0.16,
            }}
            transition={{ duration: 0.11, ease: 'easeOut' }}
          />
        );
      })}
    </div>
  );
}
