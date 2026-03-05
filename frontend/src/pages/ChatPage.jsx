import { useState, useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  Send,
  Bot,
  User,
  Sparkles,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import AuthModal from '../components/AuthModal';
import TypingIndicator from '../components/TypingIndicator';
import AnimatedPage from '../components/AnimatedPage';
import { askGeneration } from '../config/api';

export default function ChatPage() {
  const { user } = useAuth();
  const { theme } = useTheme();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [showAuthModal, setShowAuthModal] = useState(false);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping]);

  const handleSend = async () => {
    if (!input.trim()) return;
    if (!user) { setShowAuthModal(true); return; }

    const queryText = input.trim();
    const userMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: queryText,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };
    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsTyping(true);
    try {
      const chatHistory = messages
        .filter((msg) => msg.role === 'user' || msg.role === 'assistant')
        .map((msg) => ({
          role: msg.role,
          content: msg.content,
        }));

      const response = await askGeneration({
        query: queryText,
        chatHistory,
      });

      const sources = Array.isArray(response?.citations)
        ? [...new Set(response.citations.map((citation) => citation.document_name).filter(Boolean))]
        : [];

      const aiResponse = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: response?.answer || 'No answer returned by generation service.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        sources,
      };
      setMessages((prev) => [...prev, aiResponse]);
    } catch (error) {
      const aiError = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `Generation request failed: ${error.message}`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        sources: [],
      };
      setMessages((prev) => [...prev, aiError]);
    } finally {
      setIsTyping(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  return (
    <AnimatedPage className="h-full w-full flex justify-center">
      <div className="h-full w-full max-w-4xl flex flex-col px-5 md:px-8 relative md:left-20 lg:left-32 xl:left-40 mt-12 md:mt-16" style={{ minHeight: 0 }}>
      {/* Messages */}
      <div className="flex-1 w-full" style={{ overflowY: 'auto', overflowX: 'hidden', scrollBehavior: 'smooth', minHeight: 0, scrollbarGutter: 'stable', paddingTop: '32px', paddingBottom: '32px' }}>
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center max-w-3xl mx-auto w-full">
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
                className="flex items-end gap-3 rounded-2xl p-6 transition-all input-glow"
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
                  className="flex-1 bg-transparent outline-none text-[15px] resize-none max-h-56"
                  style={{ color: 'var(--text-primary)', padding: '16px 24px' }}
                />
                <motion.button
                  id="chat-send-btn"
                  onClick={handleSend}
                  disabled={!input.trim() || isTyping}
                  className="rounded-xl transition-colors disabled:opacity-20 disabled:cursor-not-allowed shrink-0"
                  style={{
                    padding: '16px 22px',
                    marginRight: '8px',
                  }}
                  whileHover={input.trim() && !isTyping ? { scale: 1.05 } : {}}
                  whileTap={{ scale: 0.95 }}
                >
                  <Send size={18} color={input.trim() && !isTyping ? '#7c3aed' : (theme === 'dark' ? 'white' : 'black')} />
                </motion.button>
              </div>
              <p className="text-xs text-center mt-3" style={{ color: 'var(--text-muted)' }}>
                AI responses are generated from indexed legal documents. Always verify with official sources.
              </p>
            </div>
          </div>
        ) : (
          <div className="max-w-2xl mx-auto">
            {messages.map((msg) => (
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
                  <p className="text-[15px] leading-relaxed my-2">{msg.content}</p>
                  {msg.sources && (
                    <div className="mt-3 pt-3" style={{ borderTop: '1px solid var(--border-color)' }}>
                      <p className="text-xs font-medium mb-1.5" style={{ color: 'var(--text-muted)' }}>Sources:</p>
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
                    </div>
                  )}
                  <p
                    className={`text-xs mt-2 ${msg.role === 'user' ? 'text-white/50' : ''}`}
                    style={msg.role === 'assistant' ? { color: 'var(--text-muted)' } : {}}
                  >
                    {msg.timestamp}
                  </p>
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
            ))}

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
      {messages.length > 0 && (
      <div className="py-3 w-full" style={{ borderColor: 'var(--border-color)', borderTop: '1px solid var(--border-color)' }}>
        <div className="max-w-2xl mx-auto">
          <div
            className="flex items-end gap-3 rounded-2xl p-6 transition-all input-glow"
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
              className="flex-1 bg-transparent outline-none text-[15px] resize-none max-h-56"
              style={{ color: 'var(--text-primary)', padding: '16px 24px' }}
            />
            <motion.button
              id="chat-send-btn"
              onClick={handleSend}
              disabled={!input.trim() || isTyping}
              className="rounded-xl transition-colors disabled:opacity-20 disabled:cursor-not-allowed shrink-0"
              style={{
                padding: '16px 22px',
                marginRight: '8px',
              }}
              whileHover={input.trim() && !isTyping ? { scale: 1.05 } : {}}
              whileTap={{ scale: 0.95 }}
            >
              <Send size={18} color={input.trim() && !isTyping ? '#7c3aed' : (theme === 'dark' ? 'white' : 'black')} />
            </motion.button>
          </div>
          <p className="text-xs text-center mt-3" style={{ color: 'var(--text-muted)' }}>
            AI responses are generated from indexed legal documents. Always verify with official sources.
          </p>
        </div>
      </div>
      )}

      <AuthModal isOpen={showAuthModal} onClose={() => setShowAuthModal(false)} />
      </div>
    </AnimatedPage>
  );
}
