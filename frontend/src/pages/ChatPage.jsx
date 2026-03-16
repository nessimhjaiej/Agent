import { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Send,
  Bot,
  User,
  Sparkles,
  Mic,
  Square,
  Pencil,
  Check,
  X,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import AuthModal from '../components/AuthModal';
import TypingIndicator from '../components/TypingIndicator';
import AnimatedPage from '../components/AnimatedPage';
import API from '../config/api';

const VOICE_WAVEFORM_BAR_COUNT = 33;

function buildUserChatSessionId(userId) {
  return `user-chat-${userId || 'guest'}`;
}

function VoiceWaveform({ isRecording, samples }) {
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

export default function ChatPage() {
  const { user } = useAuth();
  const { theme } = useTheme();
  const [messages, setMessages] = useState([]);
  const [chatSessionId, setChatSessionId] = useState(null);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [editingMessageId, setEditingMessageId] = useState(null);
  const [editingText, setEditingText] = useState('');
  const [expandedSources, setExpandedSources] = useState({});
  const [showAuthModal, setShowAuthModal] = useState(false);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const audioChunksRef = useRef([]);
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const animationFrameRef = useRef(null);
  const sourceNodeRef = useRef(null);
  const [waveformSamples, setWaveformSamples] = useState(
    () => Array.from({ length: VOICE_WAVEFORM_BAR_COUNT }, () => 0),
  );

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping]);

  useEffect(() => {
    setMessages([]);
    setChatSessionId(buildUserChatSessionId(user?.id));
  }, [user?.id]);

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

  const requestAssistantReply = async ({ query, historyMessages, nextMessages }) => {
    setMessages(nextMessages);
    setInput('');
    setIsTyping(true);
    try {
      const chatHistory = historyMessages.slice(-12).map((msg) => ({
        role: msg.role === 'assistant' ? 'assistant' : 'user',
        content: msg.content,
      }));

      const response = await fetch(`${API.generation}/ask`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query,
          mode: 'hybrid',
          chat_history: chatHistory,
          session_id: chatSessionId,
        }),
      });

      const payload = await response.json();
      if (!response.ok) {
        const detail = typeof payload?.detail === 'string' ? payload.detail : 'Request failed';
        throw new Error(detail);
      }

      const sources = Array.isArray(payload.citations)
        ? [...new Set(payload.citations.map((item) => item.document_name).filter(Boolean))]
        : [];
      const citations = Array.isArray(payload.citations) ? payload.citations : [];

      const aiResponse = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: payload.answer || 'No answer returned by generation service.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        sources,
        citations,
      };
      setMessages((prev) => [...prev, aiResponse]);
    } catch (error) {
      const fallback = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `Generation request failed: ${error?.message || 'unknown error'}`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        sources: [],
      };
      setMessages((prev) => [...prev, fallback]);
    } finally {
      setIsTyping(false);
    }
  };

  const handleSend = async () => {
    if (!input.trim()) return;
    if (!user) { setShowAuthModal(true); return; }
    const query = input.trim();
    const currentMessages = [...messages];
    const userMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: query,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    await requestAssistantReply({
      query,
      historyMessages: currentMessages,
      nextMessages: [...currentMessages, userMessage],
    });
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const startEditingMessage = (message) => {
    setEditingMessageId(message.id);
    setEditingText(message.content);
  };

  const cancelEditingMessage = () => {
    setEditingMessageId(null);
    setEditingText('');
  };

  const saveEditedMessage = () => {
    const nextContent = editingText.trim();
    if (!editingMessageId || !nextContent) return;
    const currentMessages = [...messages];
    const editedIndex = currentMessages.findIndex((message) => message.id === editingMessageId);
    if (editedIndex === -1) return;

    const updatedMessage = {
      ...currentMessages[editedIndex],
      content: nextContent,
      edited: true,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };
    const historyMessages = currentMessages.slice(0, editedIndex);
    const nextMessages = [...historyMessages, updatedMessage];
    cancelEditingMessage();
    requestAssistantReply({
      query: nextContent,
      historyMessages,
      nextMessages,
    });
  };

  const handleEditKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      saveEditedMessage();
    }
    if (e.key === 'Escape') {
      e.preventDefault();
      cancelEditingMessage();
    }
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
      setInput((prev) => (prev.trim() ? `${prev.trim()}\n${transcript}` : transcript));
      inputRef.current?.focus();
    } catch (error) {
      const fallback = {
        id: Date.now().toString(),
        role: 'assistant',
        content: `Transcription failed: ${error?.message || 'unknown error'}`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        sources: [],
      };
      setMessages((prev) => [...prev, fallback]);
    } finally {
      setIsTranscribing(false);
    }
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
  };

  const handleRecordAudio = async () => {
    if (!user) { setShowAuthModal(true); return; }
    if (isRecording || isTranscribing || isTyping) return;

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
      setIsRecording(true);
    } catch (error) {
      const fallback = {
        id: Date.now().toString(),
        role: 'assistant',
        content: `Microphone access failed: ${error?.message || 'unknown error'}`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        sources: [],
      };
      setMessages((prev) => [...prev, fallback]);
      resetRecorderState();
    }
  };

  const handleStopRecording = () => {
    if (!isRecording) return;
    mediaRecorderRef.current?.stop();
  };

  const toggleSources = (messageId) => {
    setExpandedSources((prev) => ({ ...prev, [messageId]: !prev[messageId] }));
  };

  const latestUserMessageId = [...messages].reverse().find((message) => message.role === 'user')?.id ?? null;
  const hasMessages = messages.length > 0;
  const contentAlignmentClass = 'md:translate-x-8 lg:translate-x-12 xl:translate-x-16';
  const recordButtonTitle = isRecording ? 'Stop recording' : 'Record audio for transcription';
  const recordButtonColor = isRecording
    ? '#dc2626'
    : (isTyping || isTranscribing ? (theme === 'dark' ? 'white' : 'black') : '#7c3aed');
  const renderRecordButton = () => (
    <motion.button
      type="button"
      onClick={isRecording ? handleStopRecording : handleRecordAudio}
      disabled={isTyping || isTranscribing}
      className={`voice-waveform-button rounded-xl transition-colors disabled:opacity-20 disabled:cursor-not-allowed shrink-0 ${isRecording ? 'is-recording' : 'is-idle'}`}
      style={{
        padding: isRecording ? '10px 14px 10px 28px' : '12px 14px',
      }}
      whileHover={!isTyping && !isTranscribing ? { scale: 1.03 } : {}}
      whileTap={{ scale: 0.97 }}
      title={recordButtonTitle}
    >
      {isRecording ? (
        <>
          <span className="voice-waveform-button__dot" aria-hidden="true" />
          <VoiceWaveform isRecording={isRecording} samples={waveformSamples} />
          <span className="voice-waveform-button__stop" aria-hidden="true">
            <Square size={12} color={recordButtonColor} fill={recordButtonColor} />
          </span>
        </>
      ) : (
        <Mic size={18} color={recordButtonColor} />
      )}
    </motion.button>
  );

  return (
    <AnimatedPage className="h-full w-full flex justify-center">
      <div className="h-full w-full max-w-4xl flex flex-col px-5 md:px-8 mt-12 md:mt-16" style={{ minHeight: 0 }}>
      {/* Messages */}
      <div className="flex-1 w-full" style={{ overflowY: 'auto', overflowX: 'hidden', scrollBehavior: 'smooth', minHeight: 0, scrollbarGutter: 'stable', paddingTop: '32px', paddingBottom: '32px' }}>
        {!hasMessages ? (
          <div className={`h-full flex flex-col items-center justify-center text-center max-w-3xl mx-auto w-full ${contentAlignmentClass}`}>
            {/* Animated icon */}
            <div className="relative mb-10">
              <motion.div
                className="w-24 h-24 rounded-2xl flex items-center justify-center"
                style={{
                  background: 'rgba(139,92,246,0.08)',
                  boxShadow: '0 0 40px rgba(139,92,246,0.15)',
                }}
                animate={{
                  boxShadow: [
                    '0 0 40px rgba(139,92,246,0.15)',
                    '0 0 60px rgba(139,92,246,0.25)',
                    '0 0 40px rgba(139,92,246,0.15)',
                  ],
                }}
                transition={{ duration: 3, repeat: Infinity }}
              >
                <Sparkles className="w-12 h-12" style={{ color: 'var(--color-primary-400)' }} />
              </motion.div>
              {/* Orbital dot */}
              <motion.div
                className="absolute w-3 h-3 rounded-full"
                animate={{ 
                  rotate: 360,
                }}
                transition={{ duration: 4, repeat: Infinity, ease: 'linear', repeatType: 'loop' }}
                style={{
                  background: 'linear-gradient(135deg, #a78bfa, #22d3ee)',
                  boxShadow: '0 0 10px rgba(139,92,246,0.5)',
                  top: 'calc(50% - 6px)',
                  left: 'calc(50% + 60px)',
                  transformOrigin: '-60px 6px',
                }}
              />
            </div>

            <h2 className="text-3xl md:text-4xl lg:text-5xl font-bold font-display mb-4" style={{ color: 'var(--text-primary)' }}>
              Legal Intelligence at Your{' '}
              <span className="gradient-text-animated">Fingertips</span>
            </h2>
            <p className="text-base md:text-lg max-w-lg mb-12 leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
              Ask any question about legal regulations, compliance, or regulatory frameworks.
              Our AI will retrieve and analyze relevant sources.
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 w-full max-w-2xl mb-8" style={{ marginTop: '32px' }}>
              {[
                'What are the key GDPR requirements for data controllers?',
                'Explain ICC arbitration procedures',
                'French labor law dismissal process',
                'SOX compliance requirements',
              ].map((suggestion, i) => (
                <motion.button
                  key={i}
                  onClick={() => setInput(suggestion)}
                  className="text-left text-xs rounded-xl transition-all"
                  style={{
                    border: '1px solid var(--border-color)',
                    color: 'var(--text-secondary)',
                    background: 'var(--bg-secondary)',
                    padding: '14px 18px',
                  }}
                  whileHover={{
                    borderColor: 'rgba(139,92,246,0.3)',
                    boxShadow: '0 0 20px rgba(139,92,246,0.1)',
                    y: -2,
                  }}
                  initial={{ opacity: 0, y: 15 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.2 + i * 0.1 }}
                >
                  {suggestion}
                </motion.button>
              ))}
            </div>

            {/* Input Area - Centered in Welcome */}
            <div className="w-full max-w-2xl" style={{ marginTop: '32px' }}>
              <div
                className="flex flex-col gap-4 rounded-2xl p-6 transition-all input-glow"
                style={{
                  background: 'var(--bg-secondary)',
                  border: '1px solid var(--border-color)',
                }}
              >
                <textarea
                  ref={inputRef}
                  id="chat-input"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={user ? 'Ask about legal regulations, compliance...' : 'Sign in to start a conversation...'}
                  rows={3}
                  className="w-full bg-transparent outline-none text-[15px] resize-none max-h-56"
                  style={{ color: 'var(--text-primary)', padding: '16px 8px 8px' }}
                />
                <div className="flex w-full items-center justify-end gap-2 shrink-0">
                  {renderRecordButton()}
                  <motion.button
                    id="chat-send-btn"
                    onClick={handleSend}
                    disabled={!input.trim() || isTyping || isTranscribing}
                    className="rounded-xl transition-colors disabled:opacity-20 disabled:cursor-not-allowed shrink-0"
                    style={{
                      padding: '16px 22px',
                    }}
                    whileHover={input.trim() && !isTyping ? { scale: 1.05 } : {}}
                    whileTap={{ scale: 0.95 }}
                  >
                    <Send size={18} color={input.trim() && !isTyping ? '#7c3aed' : (theme === 'dark' ? 'white' : 'black')} />
                  </motion.button>
                </div>
              </div>
              <p className="text-xs text-center mt-3" style={{ color: 'var(--text-muted)' }}>
                {isTranscribing
                  ? 'Transcribing audio with OpenAI...'
                  : isRecording
                    ? 'Recording audio... press the square button to stop.'
                  : 'AI responses are generated from indexed legal documents. Always verify with official sources.'}
              </p>
            </div>
          </div>
        ) : (
          <div className={`max-w-3xl mx-auto w-full ${contentAlignmentClass}`}>
            {messages.map((msg) => {
              const isEditing = editingMessageId === msg.id;

              return (
              <motion.div
                key={msg.id}
                className={`flex gap-4 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                style={{ marginBottom: '40px' }}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.35 }}
              >
                {msg.role === 'assistant' && (
                  <div
                    className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0 mt-1"
                    style={{
                      background: 'linear-gradient(135deg, #7c3aed, #06b6d4)',
                      boxShadow: '0 0 12px rgba(139,92,246,0.3)',
                    }}
                  >
                    <Bot size={16} className="text-white" />
                  </div>
                )}
                <div
                  className={`max-w-[75%] rounded-2xl ${
                    msg.role === 'user' ? 'rounded-br-md' : 'rounded-bl-md'
                  }`}
                  style={
                    msg.role === 'user'
                      ? {
                          background: 'linear-gradient(135deg, #7c3aed, #5b21b6)',
                          color: 'white',
                          boxShadow: '0 4px 15px rgba(139,92,246,0.2)',
                          padding: '16px 24px',
                        }
                      : {
                          background: 'var(--bg-tertiary)',
                          color: 'var(--text-primary)',
                          border: '1px solid var(--border-color)',
                          padding: '16px 24px',
                        }
                  }
                >
                  {isEditing ? (
                    <div className="my-2">
                      <textarea
                        value={editingText}
                        onChange={(e) => setEditingText(e.target.value)}
                        onKeyDown={handleEditKeyDown}
                        rows={4}
                        className="w-full bg-transparent outline-none text-[15px] resize-none"
                        style={{
                          color: msg.role === 'user' ? 'white' : 'var(--text-primary)',
                        }}
                      />
                      <div className="flex justify-end gap-2 mt-3">
                        <button
                          type="button"
                          onClick={cancelEditingMessage}
                          className="rounded-lg px-3 py-2 text-xs"
                          style={{
                            border: '1px solid rgba(255,255,255,0.2)',
                            color: msg.role === 'user' ? 'white' : 'var(--text-secondary)',
                          }}
                        >
                          <X size={14} />
                        </button>
                        <button
                          type="button"
                          onClick={saveEditedMessage}
                          disabled={!editingText.trim()}
                          className="rounded-lg px-3 py-2 text-xs disabled:opacity-30"
                          style={{
                            background: msg.role === 'user' ? 'rgba(255,255,255,0.16)' : 'rgba(124,58,237,0.14)',
                            color: msg.role === 'user' ? 'white' : 'var(--color-primary-400)',
                          }}
                        >
                          <Check size={14} />
                        </button>
                      </div>
                    </div>
                  ) : (
                    <p className="text-[15px] leading-relaxed my-2">{msg.content}</p>
                  )}
                  {msg.sources && (
                    <div className="mt-3 pt-3" style={{ borderTop: '1px solid var(--border-color)' }}>
                      <div className="flex items-center justify-between gap-3 mb-1.5">
                        <p className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>Sources:</p>
                        {msg.role === 'assistant' && Array.isArray(msg.citations) && msg.citations.length > 0 && (
                          <button
                            type="button"
                            onClick={() => toggleSources(msg.id)}
                            className="inline-flex items-center gap-1 text-xs"
                            style={{ color: 'var(--color-primary-400)' }}
                          >
                            {expandedSources[msg.id] ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                            {expandedSources[msg.id] ? 'Hide chunks' : 'Show chunks'}
                          </button>
                        )}
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {msg.sources.map((src, i) => (
                          <span
                            key={i}
                            className="text-xs px-2.5 py-0.5 rounded-full"
                            style={{
                              background: 'rgba(139,92,246,0.08)',
                              color: 'var(--color-primary-400)',
                              border: '1px solid rgba(139,92,246,0.15)',
                            }}
                          >
                            {src}
                          </span>
                        ))}
                      </div>
                      {expandedSources[msg.id] && Array.isArray(msg.citations) && msg.citations.length > 0 && (
                        <div className="mt-3 space-y-3">
                          {msg.citations.map((citation) => (
                            <div
                              key={citation.chunk_id}
                              className="rounded-xl p-3"
                              style={{
                                background: 'rgba(139,92,246,0.06)',
                                border: '1px solid rgba(139,92,246,0.12)',
                              }}
                            >
                              <p className="text-xs mb-1" style={{ color: 'var(--text-muted)' }}>
                                {citation.document_name} · {citation.chunk_id}
                              </p>
                              <p className="text-sm leading-relaxed" style={{ color: 'var(--text-primary)' }}>
                                {citation.chunk_text}
                              </p>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                  <p
                    className={`text-xs mt-2 ${msg.role === 'user' ? 'text-white/50' : ''}`}
                    style={msg.role === 'assistant' ? { color: 'var(--text-muted)' } : {}}
                  >
                    {msg.timestamp}{msg.edited ? ' • edited' : ''}
                  </p>
                  {msg.role === 'user' && !isEditing && msg.id === latestUserMessageId && (
                    <div className="mt-3 flex justify-end">
                      <button
                        type="button"
                        onClick={() => startEditingMessage(msg)}
                        disabled={isTyping || isTranscribing || isRecording}
                        className="inline-flex items-center gap-1 text-xs"
                        style={{ color: 'rgba(255,255,255,0.7)' }}
                      >
                        <Pencil size={12} />
                        Edit
                      </button>
                    </div>
                  )}
                </div>
                {msg.role === 'user' && (
                  <div
                    className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0 mt-1"
                    style={{
                      background: 'linear-gradient(135deg, #52525b, #27272a)',
                    }}
                  >
                    <User size={16} className="text-white" />
                  </div>
                )}
              </motion.div>
            );
            })}

            {isTyping && (
              <motion.div className="flex gap-4" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
                <div
                  className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
                  style={{
                    background: 'linear-gradient(135deg, #7c3aed, #06b6d4)',
                    boxShadow: '0 0 12px rgba(139,92,246,0.3)',
                  }}
                >
                  <Bot size={16} className="text-white" />
                </div>
                <div
                  className="rounded-2xl rounded-bl-md"
                  style={{
                    background: 'var(--bg-tertiary)',
                    border: '1px solid var(--border-color)',
                    padding: '16px 24px',
                  }}
                >
                  <TypingIndicator />
                </div>
              </motion.div>
            )}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Input Area - Footer for conversation */}
      {hasMessages && (
      <div className="py-3 w-full">
        <div className={`max-w-3xl mx-auto w-full ${contentAlignmentClass}`}>
          <div
            className="flex flex-col gap-4 rounded-2xl p-6 transition-all input-glow"
            style={{
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border-color)',
            }}
          >
            <textarea
              ref={inputRef}
              id="chat-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={user ? 'Ask about legal regulations, compliance...' : 'Sign in to start a conversation...'}
              rows={3}
              className="w-full bg-transparent outline-none text-[15px] resize-none max-h-56"
              style={{ color: 'var(--text-primary)', padding: '16px 8px 8px' }}
            />
            <div className="flex w-full items-center justify-end gap-2 shrink-0">
              {renderRecordButton()}
              <motion.button
                id="chat-send-btn"
                onClick={handleSend}
                disabled={!input.trim() || isTyping || isTranscribing}
                className="rounded-xl transition-colors disabled:opacity-20 disabled:cursor-not-allowed shrink-0"
                style={{
                  padding: '16px 22px',
                }}
                whileHover={input.trim() && !isTyping ? { scale: 1.05 } : {}}
                whileTap={{ scale: 0.95 }}
              >
                <Send size={18} color={input.trim() && !isTyping ? '#7c3aed' : (theme === 'dark' ? 'white' : 'black')} />
              </motion.button>
            </div>
          </div>
          <p className="text-xs text-center mt-3" style={{ color: 'var(--text-muted)' }}>
            {isTranscribing
              ? 'Transcribing audio with OpenAI...'
              : isRecording
                ? 'Recording audio... press the square button to stop.'
              : 'AI responses are generated from indexed legal documents. Always verify with official sources.'}
          </p>
        </div>
      </div>
      )}

      <AuthModal isOpen={showAuthModal} onClose={() => setShowAuthModal(false)} />
      </div>
    </AnimatedPage>
  );
}
