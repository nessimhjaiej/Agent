import { useState, useRef, useEffect } from 'react';
import API from '../config/api';

export const VOICE_WAVEFORM_BAR_COUNT = 33;

/**
 * Records microphone audio and transcribes it via the generation service.
 *
 * Wiring is left to the caller through callbacks so the same logic can back
 * both the user chat and the admin chat:
 *   - onTranscript(text): receives the recognized text to insert.
 *   - onError(message):   receives a human-readable error (mic / transcription).
 *   - canRecord():        optional gate; return false to block starting (the
 *                         caller can also run side effects, e.g. an auth modal).
 */
export function useVoiceTranscription({ onTranscript, onError, canRecord } = {}) {
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [recordingElapsedSeconds, setRecordingElapsedSeconds] = useState(0);
  const [waveformSamples, setWaveformSamples] = useState(
    () => Array.from({ length: VOICE_WAVEFORM_BAR_COUNT }, () => 0),
  );

  const mediaRecorderRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const audioChunksRef = useRef([]);
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const animationFrameRef = useRef(null);
  const sourceNodeRef = useRef(null);
  const recordingStartedAtRef = useRef(null);

  // Tear everything down if the component using the hook unmounts mid-recording.
  useEffect(() => () => {
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
    }
    sourceNodeRef.current?.disconnect?.();
    analyserRef.current?.disconnect?.();
    audioContextRef.current?.close?.();
    mediaRecorderRef.current?.stop?.();
    mediaStreamRef.current?.getTracks?.().forEach((track) => track.stop());
  }, []);

  useEffect(() => {
    if (!isRecording) {
      return undefined;
    }

    const intervalId = window.setInterval(() => {
      if (!recordingStartedAtRef.current) return;
      const elapsedSeconds = Math.floor((Date.now() - recordingStartedAtRef.current) / 1000);
      setRecordingElapsedSeconds(elapsedSeconds);
    }, 1000);

    return () => window.clearInterval(intervalId);
  }, [isRecording]);

  const stopAudioLevelTracking = () => {
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
    sourceNodeRef.current?.disconnect?.();
    analyserRef.current?.disconnect?.();
    sourceNodeRef.current = null;
    analyserRef.current = null;
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
    setWaveformSamples(Array.from({ length: VOICE_WAVEFORM_BAR_COUNT }, () => 0));
  };

  const startAudioLevelTracking = async (stream) => {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return;

    stopAudioLevelTracking();

    const audioContext = new AudioContextClass();
    const analyser = audioContext.createAnalyser();
    const sourceNode = audioContext.createMediaStreamSource(stream);

    analyser.fftSize = 256;
    analyser.smoothingTimeConstant = 0.72;
    sourceNode.connect(analyser);

    const dataArray = new Uint8Array(analyser.fftSize);

    const updateLevel = () => {
      analyser.getByteTimeDomainData(dataArray);
      let sumSquares = 0;

      for (let i = 0; i < dataArray.length; i += 1) {
        const normalized = (dataArray[i] - 128) / 128;
        sumSquares += normalized * normalized;
      }

      const rms = Math.sqrt(sumSquares / dataArray.length);
      const boostedLevel = Math.min(1, Math.pow(rms * 8, 0.9));
      const smoothedLevel = Math.min(1, boostedLevel * 0.82);
      setWaveformSamples((prev) => {
        const nextSample = smoothedLevel > 0.06 ? smoothedLevel : 0;
        return [...prev.slice(1), nextSample];
      });
      animationFrameRef.current = requestAnimationFrame(updateLevel);
    };

    audioContextRef.current = audioContext;
    analyserRef.current = analyser;
    sourceNodeRef.current = sourceNode;

    if (audioContext.state === 'suspended') {
      await audioContext.resume();
    }

    updateLevel();
  };

  const resetRecorderState = () => {
    stopAudioLevelTracking();
    mediaRecorderRef.current = null;
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
    audioChunksRef.current = [];
    setIsRecording(false);
    setRecordingElapsedSeconds(0);
    recordingStartedAtRef.current = null;
  };

  const formatRecordingTimer = (elapsedSeconds) => {
    const minutes = Math.floor(elapsedSeconds / 60);
    const seconds = elapsedSeconds % 60;
    return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  };

  const submitAudioForTranscription = async (file) => {
    setIsTranscribing(true);
    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch(`${API.generation}/transcribe`, {
        method: 'POST',
        body: formData,
      });

      const payload = await response.json();
      if (!response.ok) {
        const detail = typeof payload?.detail === 'string' ? payload.detail : 'Transcription failed';
        throw new Error(detail);
      }

      const transcript = typeof payload?.text === 'string' ? payload.text.trim() : '';
      if (!transcript) {
        throw new Error('No transcript returned');
      }
      onTranscript?.(transcript);
    } catch (error) {
      onError?.(`Transcription failed: ${error?.message || 'unknown error'}`);
    } finally {
      setIsTranscribing(false);
    }
  };

  const startRecording = async () => {
    if (canRecord && !canRecord()) return;
    if (isRecording || isTranscribing) return;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MediaRecorder.isTypeSupported('audio/webm')
        ? 'audio/webm'
        : '';
      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);

      mediaStreamRef.current = stream;
      mediaRecorderRef.current = recorder;
      audioChunksRef.current = [];
      await startAudioLevelTracking(stream);

      recorder.addEventListener('dataavailable', (event) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      });

      recorder.addEventListener('stop', async () => {
        const recordedType = recorder.mimeType || 'audio/webm';
        const extension = recordedType.includes('mp4') ? 'm4a' : 'webm';
        const audioBlob = new Blob(audioChunksRef.current, { type: recordedType });
        resetRecorderState();
        if (audioBlob.size === 0) {
          return;
        }
        await submitAudioForTranscription(
          new File([audioBlob], `recording.${extension}`, { type: recordedType }),
        );
      });

      recorder.start();
      recordingStartedAtRef.current = Date.now();
      setRecordingElapsedSeconds(0);
      setIsRecording(true);
    } catch (error) {
      onError?.(`Microphone access failed: ${error?.message || 'unknown error'}`);
      resetRecorderState();
    }
  };

  const stopRecording = () => {
    if (!isRecording) return;
    mediaRecorderRef.current?.stop();
  };

  return {
    isRecording,
    isTranscribing,
    recordingElapsedSeconds,
    waveformSamples,
    startRecording,
    stopRecording,
    formatRecordingTimer,
  };
}
