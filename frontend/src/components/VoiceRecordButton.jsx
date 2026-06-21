import { motion } from 'framer-motion';
import { Mic, Square } from 'lucide-react';
import VoiceWaveform from './VoiceWaveform';

/**
 * Mic / stop button with an inline live waveform + timer while recording.
 * Presentational only — state and handlers come from useVoiceTranscription.
 */
export default function VoiceRecordButton({
  isRecording,
  isTranscribing,
  disabled,
  elapsedSeconds,
  waveformSamples,
  formatTimer,
  onStart,
  onStop,
  theme,
}) {
  const title = isRecording ? 'Stop recording' : 'Record audio for transcription';
  const color = isRecording
    ? '#dc2626'
    : (disabled || isTranscribing ? (theme === 'dark' ? 'white' : 'black') : '#7c3aed');

  return (
    <motion.button
      type="button"
      onClick={isRecording ? onStop : onStart}
      disabled={disabled || isTranscribing}
      className={`voice-waveform-button rounded-xl transition-all duration-200 disabled:opacity-20 disabled:cursor-not-allowed shrink-0 ${isRecording ? 'is-recording' : 'is-idle'}`}
      style={{ padding: isRecording ? '10px 14px 10px 28px' : '12px 14px' }}
      whileHover={{}}
      whileTap={{ scale: 0.97 }}
      title={title}
    >
      {isRecording ? (
        <>
          <span className="voice-waveform-button__dot" aria-hidden="true" />
          <span
            className="voice-waveform-button__timer"
            aria-label={`Recording time ${formatTimer(elapsedSeconds)}`}
          >
            {formatTimer(elapsedSeconds)}
          </span>
          <VoiceWaveform isRecording={isRecording} samples={waveformSamples} />
          <span className="voice-waveform-button__stop" aria-hidden="true">
            <Square className="voice-waveform-button__icon" size={12} color={color} fill={color} />
          </span>
        </>
      ) : (
        <Mic className="voice-waveform-button__icon" size={18} color={color} />
      )}
    </motion.button>
  );
}
