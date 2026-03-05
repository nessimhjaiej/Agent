import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { FileText, Check, X, Clock, Search, Upload, Send, Bot, User, Eye, Trash2 } from 'lucide-react';
import AnimatedPage from '../components/AnimatedPage';
import TypingIndicator from '../components/TypingIndicator';
import { useTheme } from '../context/ThemeContext';

const MOCK_DOCUMENTS = [
  { id: '1', name: 'GDPR_Regulation_EU_2016_679.pdf', status: 'validated', size: '2.3 MB', date: '2026-02-15', chunks: 142 },
  { id: '2', name: 'French_Labor_Code_2025.pdf', status: 'validated', size: '5.1 MB', date: '2026-02-12', chunks: 389 },
  { id: '3', name: 'ICC_Arbitration_Rules_2021.pdf', status: 'pending', size: '1.8 MB', date: '2026-03-01', chunks: 0 },
  { id: '4', name: 'SOX_Compliance_Guide.pdf', status: 'pending', size: '3.2 MB', date: '2026-03-02', chunks: 0 },
  { id: '5', name: 'Anti_Money_Laundering_Directive.pdf', status: 'validated', size: '1.5 MB', date: '2026-01-20', chunks: 98 },
  { id: '6', name: 'Basel_III_Framework.pdf', status: 'rejected', size: '4.7 MB', date: '2026-02-28', chunks: 0 },
];

const AGENT_RESPONSES = [
  "✅ Document added to ingestion queue. It will be preprocessed, chunked, and embedded shortly.",
  "🔄 Re-embedding initiated. Estimated: ~15 minutes for 629 chunks.",
  "📊 Status: 5 documents indexed, 629 chunks, avg latency 120ms.",
  "🗑️ Document removed. Chunks and embeddings cleaned up.",
];

function StatusBadge({ status }) {
  const cfg = {
    validated: { bg: 'rgba(16,185,129,0.1)', text: '#10b981', border: 'rgba(16,185,129,0.2)', icon: Check, label: 'Validated' },
    pending: { bg: 'rgba(245,158,11,0.1)', text: '#f59e0b', border: 'rgba(245,158,11,0.2)', icon: Clock, label: 'Pending' },
    rejected: { bg: 'rgba(239,68,68,0.1)', text: '#ef4444', border: 'rgba(239,68,68,0.2)', icon: X, label: 'Rejected' },
  }[status];
  const Icon = cfg.icon;
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium"
      style={{ background: cfg.bg, color: cfg.text, border: `1px solid ${cfg.border}` }}
    >
      <Icon size={11} /> {cfg.label}
    </span>
  );
}

export default function AdminPage() {
  const { theme } = useTheme();
  const [tab, setTab] = useState('documents');
  const [docs, setDocs] = useState(MOCK_DOCUMENTS);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
  const [agentMsgs, setAgentMsgs] = useState([{
    id: '0', role: 'assistant', timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    content: "👋 I'm the Admin Agent. Try:\n• \"Add a new document\"\n• \"Re-embed the database\"\n• \"Show system status\"",
  }]);
  const [agentInput, setAgentInput] = useState('');
  const [typing, setTyping] = useState(false);
  const endRef = useRef(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [agentMsgs, typing]);

  const filtered = docs.filter(d =>
    d.name.toLowerCase().includes(search.toLowerCase()) && (filter === 'all' || d.status === filter)
  );

  const sendAgent = () => {
    if (!agentInput.trim()) return;
    setAgentMsgs(p => [...p, { id: Date.now().toString(), role: 'user', content: agentInput, timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }]);
    setAgentInput(''); setTyping(true);
    setTimeout(() => {
      setAgentMsgs(p => [...p, { id: (Date.now()+1).toString(), role: 'assistant', content: AGENT_RESPONSES[Math.floor(Math.random()*AGENT_RESPONSES.length)], timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }]);
      setTyping(false);
    }, 1200 + Math.random() * 1000);
  };

  const tabs = [
    { key: 'documents', label: 'Document Management', icon: FileText },
    { key: 'agent', label: 'Admin Agent Chat', icon: Bot },
  ];

  return (
    <AnimatedPage className="h-full flex flex-col">
      <div className="w-full h-full flex flex-col items-center" style={{ minHeight: 0 }}>
        {/* Tabs */}
        <div className="flex gap-0 shrink-0 max-w-5xl mx-auto px-5 md:px-8" style={{ marginBottom: '24px' }}>
        {tabs.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className="flex items-center gap-2 px-6 text-sm font-medium transition-all"
            style={{
              background: tab === key ? 'linear-gradient(135deg, #7c3aed, #06b6d4)' : 'var(--bg-secondary)',
              border: tab === key ? 'none' : '1px solid var(--border-color)',
              color: tab === key ? 'white' : 'var(--text-secondary)',
              boxShadow: tab === key ? '0 0 20px rgba(139,92,246,0.3)' : 'none',
              borderRadius: key === 'documents' ? '12px 0 0 50px' : key === 'agent' ? '0 12px 50px 0' : '12px',
              padding: '16px 24px',
              minHeight: '56px',
              display: 'flex',
              alignItems: 'center',
            }}
          >
            <Icon size={16} /> {label}
          </button>
        ))}
      </div>

      <div className="flex-1 w-screen flex justify-center" style={{ minHeight: 0 }}>
        <AnimatePresence mode="wait">
          {tab === 'documents' ? (
            <motion.div key="docs" className="h-full w-full flex justify-center" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              <div className="h-full w-full max-w-5xl flex flex-col px-5 md:px-8 mt-8 md:mt-12 overflow-auto" style={{ minHeight: 0 }}>
              {/* Toolbar */}
              <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 shrink-0" style={{ marginTop: '24px', marginBottom: '16px' }}>
                <div
                  className="flex items-center gap-2 flex-1 w-full sm:w-auto px-4 rounded-xl transition-all input-glow"
                  style={{ border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', minHeight: '48px', display: 'flex', alignItems: 'center' }}
                >
                  <Search size={16} style={{ color: 'var(--text-muted)' }} />
                  <input id="doc-search" type="text" placeholder="Search documents..." value={search} onChange={e => setSearch(e.target.value)} className="flex-1 bg-transparent outline-none text-sm" style={{ color: 'var(--text-primary)' }} />
                </div>
                <div className="flex items-center gap-2">
                  <select id="status-filter" value={filter} onChange={e => setFilter(e.target.value)} className="px-4 rounded-xl text-sm outline-none" style={{ border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', color: 'var(--text-primary)', minHeight: '48px', minWidth: '160px', display: 'flex', alignItems: 'center', textAlign: 'center' }}>
                    <option value="all">All Status</option>
                    <option value="validated">Validated</option>
                    <option value="pending">Pending</option>
                    <option value="rejected">Rejected</option>
                  </select>
                  <motion.button
                    id="upload-btn"
                    className="flex items-center gap-2 px-6 rounded-xl text-sm font-medium text-white"
                    style={{
                      background: 'linear-gradient(135deg, #7c3aed, #06b6d4)',
                      boxShadow: '0 0 15px rgba(139,92,246,0.2)',
                      minHeight: '48px',
                      minWidth: '140px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                    whileHover={{ boxShadow: '0 0 25px rgba(139,92,246,0.4)', scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                  >
                    <Upload size={16} /><span className="hidden sm:inline">Upload</span>
                  </motion.button>
                </div>
              </div>

              {/* Stats */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 shrink-0" style={{ marginBottom: '16px' }}>
                {[
                  { l: 'Total', v: docs.length, gradient: 'linear-gradient(135deg, rgba(139,92,246,0.1), rgba(6,182,212,0.05))', color: 'var(--color-primary-400)' },
                  { l: 'Validated', v: docs.filter(d=>d.status==='validated').length, gradient: 'rgba(16,185,129,0.08)', color: '#10b981' },
                  { l: 'Pending', v: docs.filter(d=>d.status==='pending').length, gradient: 'rgba(245,158,11,0.08)', color: '#f59e0b' },
                  { l: 'Chunks', v: docs.reduce((s,d)=>s+d.chunks,0), gradient: 'rgba(59,130,246,0.08)', color: '#3b82f6' },
                ].map((s,i) => (
                  <motion.div
                    key={i}
                    className="rounded-xl"
                    style={{
                      background: 'var(--bg-secondary)',
                      border: '1px solid var(--border-color)',
                      padding: '16px',
                    }}
                    initial={{ opacity: 0, y: 15 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.08 }}
                    whileHover={{ borderColor: 'rgba(139,92,246,0.2)', boxShadow: '0 0 15px rgba(139,92,246,0.08)' }}
                  >
                    <p className="text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>{s.l}</p>
                    <p className="text-2xl font-bold font-display" style={{ color: s.color }}>{s.v}</p>
                  </motion.div>
                ))}
              </div>

              {/* Table */}
              <div className="flex-1 overflow-auto rounded-xl" style={{ border: '1px solid var(--border-color)', marginTop: '16px' }}>
                <table className="w-full text-sm">
                  <thead>
                    <tr style={{ background: 'var(--bg-tertiary)', borderBottom: '1px solid var(--border-color)' }}>
                      <th className="px-4 py-3 text-left font-semibold" style={{ color: 'var(--text-secondary)' }}>Document</th>
                      <th className="px-4 py-3 text-left font-semibold hidden md:table-cell" style={{ color: 'var(--text-secondary)' }}>Size</th>
                      <th className="px-4 py-3 text-left font-semibold hidden sm:table-cell" style={{ color: 'var(--text-secondary)' }}>Date</th>
                      <th className="px-4 py-3 text-left font-semibold" style={{ color: 'var(--text-secondary)' }}>Status</th>
                      <th className="px-4 py-3 text-right font-semibold" style={{ color: 'var(--text-secondary)' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map(doc => (
                      <motion.tr
                        key={doc.id}
                        className="transition-colors"
                        style={{ borderBottom: '1px solid var(--border-color)' }}
                        whileHover={{ background: 'rgba(139,92,246,0.03)' }}
                      >
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-3">
                            <div
                              className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
                              style={{ background: 'rgba(139,92,246,0.08)' }}
                            >
                              <FileText size={14} style={{ color: 'var(--color-primary-400)' }} />
                            </div>
                            <span className="font-medium truncate max-w-50" style={{ color: 'var(--text-primary)' }}>{doc.name}</span>
                          </div>
                        </td>
                        <td className="px-4 py-3 hidden md:table-cell" style={{ color: 'var(--text-secondary)' }}>{doc.size}</td>
                        <td className="px-4 py-3 hidden sm:table-cell" style={{ color: 'var(--text-secondary)' }}>{doc.date}</td>
                        <td className="px-4 py-3"><StatusBadge status={doc.status} /></td>
                        <td className="px-4 py-3">
                          <div className="flex items-center justify-end gap-1">
                            <button className="p-1.5 rounded-lg hover:bg-primary-500/10 transition-colors" style={{ color: 'var(--color-primary-400)' }} title="View"><Eye size={14} /></button>
                            {doc.status === 'pending' && (
                              <button className="p-1.5 rounded-lg hover:bg-success/10 text-success transition-colors" title="Validate"
                                onClick={() => setDocs(p => p.map(d => d.id === doc.id ? { ...d, status: 'validated', chunks: Math.floor(Math.random()*200+50) } : d))}
                              ><Check size={14} /></button>
                            )}
                            <button className="p-1.5 rounded-lg hover:bg-danger/10 text-danger transition-colors" title="Delete"
                              onClick={() => setDocs(p => p.filter(d => d.id !== doc.id))}
                            ><Trash2 size={14} /></button>
                          </div>
                        </td>
                      </motion.tr>
                    ))}
                  </tbody>
                </table>
                {filtered.length === 0 && (
                  <div className="text-center py-12" style={{ color: 'var(--text-muted)' }}>
                    <FileText className="w-12 h-12 mx-auto mb-3 opacity-30" />
                    <p className="text-sm">No documents found</p>
                  </div>
                )}
              </div>
              </div>
            </motion.div>
          ) : (
            <motion.div key="agent" className="h-full w-full flex justify-center" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              <div className="h-full w-full max-w-5xl flex flex-col px-5 md:px-8 relative md:left-10 lg:left-16 xl:left-20 mt-12 md:mt-16" style={{ minHeight: 0 }}>
              <div className="flex-1 w-full" style={{ overflowY: 'auto', overflowX: 'hidden', scrollBehavior: 'smooth', minHeight: 0, scrollbarGutter: 'stable', paddingTop: '32px', paddingBottom: '32px' }}>
                <div className="max-w-3xl ml-auto md:translate-x-28 lg:translate-x-40">
                  {agentMsgs.map(msg => (
                    <motion.div key={msg.id} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : ''}`} style={{ marginBottom: '32px' }} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
                      {msg.role === 'assistant' && (
                        <div
                          className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mt-1"
                          style={{
                            background: 'linear-gradient(135deg, #f59e0b, #ef4444)',
                            boxShadow: '0 0 12px rgba(245,158,11,0.3)',
                          }}
                        >
                          <Bot size={15} className="text-white" />
                        </div>
                      )}
                      <div
                        className={`max-w-[80%] rounded-2xl ${msg.role === 'user' ? 'rounded-br-md' : 'rounded-bl-md'}`}
                        style={msg.role === 'user'
                          ? { background: 'linear-gradient(135deg, #7c3aed, #5b21b6)', color: 'white', boxShadow: '0 4px 15px rgba(139,92,246,0.2)', padding: '16px 24px' }
                          : { background: 'var(--bg-tertiary)', color: 'var(--text-primary)', border: '1px solid var(--border-color)', padding: '16px 24px' }
                        }
                      >
                        <p className="text-sm leading-relaxed whitespace-pre-line my-2">{msg.content}</p>
                        <p className={`text-xs mt-2 ${msg.role === 'user' ? 'text-white/50' : ''}`} style={msg.role === 'assistant' ? { color: 'var(--text-muted)' } : {}}>{msg.timestamp}</p>
                      </div>
                      {msg.role === 'user' && (
                        <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mt-1" style={{ background: 'linear-gradient(135deg, #52525b, #27272a)' }}>
                          <User size={15} className="text-white" />
                        </div>
                      )}
                    </motion.div>
                  ))}
                  {typing && (
                    <motion.div className="flex gap-3" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                      <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0" style={{ background: 'linear-gradient(135deg, #f59e0b, #ef4444)', boxShadow: '0 0 12px rgba(245,158,11,0.3)' }}>
                        <Bot size={15} className="text-white" />
                      </div>
                      <div className="rounded-2xl rounded-bl-md" style={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-color)', padding: '16px 24px' }}>
                        <TypingIndicator />
                      </div>
                    </motion.div>
                  )}
                  <div ref={endRef} />
                </div>
              </div>
              <div className="py-3 w-full relative -translate-y-3 md:-translate-y-5">
                <div className="max-w-3xl mx-auto md:translate-x-28 lg:translate-x-40">
                    <div
                      className="flex items-end gap-3 rounded-2xl p-6 transition-all input-glow"
                      style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)' }}
                    >
                      <textarea id="admin-agent-input" value={agentInput} onChange={e => setAgentInput(e.target.value)}
                        onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendAgent(); } }}
                        placeholder='Try: "Add document" or "Re-embed database"' rows={3}
                        className="flex-1 bg-transparent outline-none text-sm resize-none max-h-56" style={{ color: 'var(--text-primary)', padding: '16px 24px' }}
                      />
                      <motion.button id="admin-send" onClick={sendAgent} disabled={!agentInput.trim() || typing}
                        className="rounded-xl disabled:opacity-20 shrink-0"
                        style={{
                          padding: '16px 22px',
                          marginRight: '8px',
                        }}
                        whileHover={agentInput.trim() && !typing ? { scale: 1.05 } : {}}
                        whileTap={{ scale: 0.95 }}
                      >
                        <Send size={16} color={agentInput.trim() && !typing ? '#7c3aed' : (theme === 'dark' ? 'white' : 'black')} />
                      </motion.button>
                    </div>
                  </div>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
      </div>
    </AnimatedPage>
  );
}
