import { useEffect, useMemo, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  FileText,
  Check,
  X,
  Clock,
  Search,
  Send,
  Bot,
  User,
  Upload,
  Eye,
  Trash2,
  RefreshCw,
} from 'lucide-react';
import AnimatedPage from '../components/AnimatedPage';
import TypingIndicator from '../components/TypingIndicator';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import { askGeneration, indexDocument } from '../config/api';

const DOCS_BUCKET = import.meta.env.VITE_SUPABASE_DOCS_BUCKET || 'documents';
const DOCS_TABLE = import.meta.env.VITE_SUPABASE_DOCS_TABLE || 'documents';

function formatBytes(bytes) {
  if (!bytes || Number.isNaN(bytes)) return '-';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(value) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '-';
  return new Intl.DateTimeFormat([], { year: 'numeric', month: '2-digit', day: '2-digit' }).format(date);
}

function mapRow(row) {
  return {
    id: row.id,
    name: row.original_name || row.storage_path?.split('/').pop() || 'unknown',
    status: row.status || 'pending',
    storagePath: row.storage_path,
    date: formatDate(row.created_at),
    size: formatBytes(row.size_bytes),
    embedded: Boolean(row.embedded),
  };
}

function StatusBadge({ status }) {
  const cfg = {
    validated: { bg: 'rgba(16,185,129,0.1)', text: '#10b981', border: 'rgba(16,185,129,0.2)', icon: Check, label: 'Validated' },
    pending: { bg: 'rgba(245,158,11,0.1)', text: '#f59e0b', border: 'rgba(245,158,11,0.2)', icon: Clock, label: 'Pending' },
    rejected: { bg: 'rgba(239,68,68,0.1)', text: '#ef4444', border: 'rgba(239,68,68,0.2)', icon: X, label: 'Rejected' },
  }[status];
  const Icon = cfg.icon;
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium" style={{ background: cfg.bg, color: cfg.text, border: `1px solid ${cfg.border}` }}>
      <Icon size={11} /> {cfg.label}
    </span>
  );
}

export default function AdminPage() {
  const { theme } = useTheme();
  const { supabase, user } = useAuth();
  const fileInputRef = useRef(null);
  const [tab, setTab] = useState('documents');
  const [docs, setDocs] = useState([]);
  const [loadingDocs, setLoadingDocs] = useState(false);
  const [busyDocIds, setBusyDocIds] = useState(new Set());
  const [embeddingValidated, setEmbeddingValidated] = useState(false);
  const [docsError, setDocsError] = useState('');
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
  const [selectedDocIds, setSelectedDocIds] = useState(new Set());
  const [agentMsgs, setAgentMsgs] = useState([
    {
      id: '0',
      role: 'assistant',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      content: 'Documents now track embedded state in Supabase. Validate to index once, then it is skipped.',
    },
  ]);
  const [agentInput, setAgentInput] = useState('');
  const [typing, setTyping] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewUrl, setPreviewUrl] = useState('');
  const [previewName, setPreviewName] = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);
  const dragDepthRef = useRef(0);
  const endRef = useRef(null);

  const markBusy = (docId, value) => {
    setBusyDocIds((prev) => {
      const next = new Set(prev);
      if (value) next.add(docId);
      else next.delete(docId);
      return next;
    });
  };

  const loadDocuments = async () => {
    if (!supabase || !user) return;
    setLoadingDocs(true);
    setDocsError('');
    try {
      const { data, error } = await supabase
        .from(DOCS_TABLE)
        .select('id, user_id, original_name, storage_path, status, embedded, size_bytes, created_at')
        .eq('user_id', user.id)
        .order('created_at', { ascending: false });
      if (error) throw error;
      const mapped = (data || []).map(mapRow);
      setDocs(mapped);
      setSelectedDocIds((prev) => {
        const allowed = new Set(mapped.map((doc) => doc.id));
        return new Set([...prev].filter((id) => allowed.has(id)));
      });
    } catch (error) {
      setDocsError(`Failed to load from Supabase table '${DOCS_TABLE}': ${error.message}`);
    } finally {
      setLoadingDocs(false);
    }
  };

  useEffect(() => {
    loadDocuments();
  }, [supabase, user]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [agentMsgs, typing]);

  const filtered = useMemo(
    () =>
      docs.filter(
        (d) =>
          d.name.toLowerCase().includes(search.toLowerCase()) &&
          (filter === 'all' || d.status === filter)
      ),
    [docs, search, filter]
  );

  const allFilteredSelected = filtered.length > 0 && filtered.every((doc) => selectedDocIds.has(doc.id));

  const toggleDocSelection = (docId) => {
    setSelectedDocIds((prev) => {
      const next = new Set(prev);
      if (next.has(docId)) next.delete(docId);
      else next.add(docId);
      return next;
    });
  };

  const toggleSelectAllFiltered = () => {
    setSelectedDocIds((prev) => {
      const next = new Set(prev);
      if (allFilteredSelected) {
        filtered.forEach((doc) => next.delete(doc.id));
      } else {
        filtered.forEach((doc) => next.add(doc.id));
      }
      return next;
    });
  };

  const uploadFiles = async (files) => {
    if (!supabase || !user || !files?.length) return;
    setDocsError('');
    try {
      for (const file of files) {
        const sanitized = file.name.replace(/\s+/g, '_');
        const storagePath = `pending/${user.id}/${Date.now()}-${sanitized}`;
        const { error: upErr } = await supabase.storage.from(DOCS_BUCKET).upload(storagePath, file, { upsert: false });
        if (upErr) throw upErr;

        const { error: rowErr } = await supabase.from(DOCS_TABLE).insert({
          user_id: user.id,
          original_name: file.name,
          storage_path: storagePath,
          status: 'pending',
          embedded: false,
          size_bytes: file.size,
        });
        if (rowErr) throw rowErr;
      }
      await loadDocuments();
    } catch (error) {
      setDocsError(error.message);
    }
  };

  const handleDrop = async (event) => {
    event.preventDefault();
    event.stopPropagation();
    dragDepthRef.current = 0;
    setIsDragging(false);
    const files = event.dataTransfer?.files;
    if (files?.length) {
      await uploadFiles(files);
    }
  };

  const handleDragOver = (event) => {
    event.preventDefault();
    event.stopPropagation();
  };

  const handleDragEnter = (event) => {
    event.preventDefault();
    event.stopPropagation();
    dragDepthRef.current += 1;
    if (dragDepthRef.current > 0) {
      setIsDragging(true);
    }
  };

  const handleDragLeave = (event) => {
    event.preventDefault();
    event.stopPropagation();
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
    if (dragDepthRef.current === 0) {
      setIsDragging(false);
    }
  };

  const moveDocument = async (doc, targetStatus) => {
    if (!supabase || !user) throw new Error('Supabase not configured');
    const filename = doc.storagePath.split('/').pop();
    const targetPath = `${targetStatus}/${user.id}/${filename}`;

    if (doc.storagePath !== targetPath) {
      const { error: moveErr } = await supabase.storage.from(DOCS_BUCKET).move(doc.storagePath, targetPath);
      if (moveErr) throw moveErr;
    }

    const { error: updErr } = await supabase
      .from(DOCS_TABLE)
      .update({
        storage_path: targetPath,
        status: targetStatus,
        embedded: targetStatus === 'validated' ? doc.embedded : false,
      })
      .eq('id', doc.id);
    if (updErr) throw updErr;
    return targetPath;
  };

  const indexValidatedDoc = async (storagePath) => {
    if (!supabase) throw new Error('Supabase not configured');
    const { data: signedData, error: signedErr } = await supabase.storage.from(DOCS_BUCKET).createSignedUrl(storagePath, 3600);
    if (signedErr) throw signedErr;
    return indexDocument({
      source_url: signedData.signedUrl,
      target_relative_path: `supabase/${storagePath}`,
      skip_if_exists: true,
    });
  };

  const validateDocument = async (doc) => {
    markBusy(doc.id, true);
    setDocsError('');
    try {
      const validatedPath = doc.status === 'validated' ? doc.storagePath : await moveDocument(doc, 'validated');
      if (!doc.embedded) {
        const result = await indexValidatedDoc(validatedPath);
        if (result.status === 'indexed' || result.status === 'already_exists') {
          const { error: updErr } = await supabase.from(DOCS_TABLE).update({
            embedded: true,
            embedded_at: new Date().toISOString(),
          }).eq('id', doc.id);
          if (updErr) throw updErr;
        }
      }
      await loadDocuments();
    } catch (error) {
      setDocsError(error.message);
    } finally {
      markBusy(doc.id, false);
    }
  };

  const rejectDocument = async (doc) => {
    markBusy(doc.id, true);
    setDocsError('');
    try {
      await moveDocument(doc, 'rejected');
      await loadDocuments();
    } catch (error) {
      setDocsError(error.message);
    } finally {
      markBusy(doc.id, false);
    }
  };

  const removeDocument = async (doc) => {
    if (!supabase) return;
    markBusy(doc.id, true);
    setDocsError('');
    try {
      const { error: rmErr } = await supabase.storage.from(DOCS_BUCKET).remove([doc.storagePath]);
      if (rmErr) throw rmErr;
      const { error: delErr } = await supabase.from(DOCS_TABLE).delete().eq('id', doc.id);
      if (delErr) throw delErr;
      await loadDocuments();
    } catch (error) {
      setDocsError(error.message);
    } finally {
      markBusy(doc.id, false);
    }
  };

  const viewDocument = async (doc) => {
    if (!supabase) return;
    markBusy(doc.id, true);
    setDocsError('');
    setPreviewLoading(true);
    try {
      const { data, error } = await supabase.storage.from(DOCS_BUCKET).createSignedUrl(doc.storagePath, 3600);
      if (error) throw error;
      setPreviewUrl(data.signedUrl);
      setPreviewName(doc.name);
      setPreviewOpen(true);
    } catch (error) {
      setDocsError(error.message);
    } finally {
      setPreviewLoading(false);
      markBusy(doc.id, false);
    }
  };

  const embedAllValidated = async () => {
    setEmbeddingValidated(true);
    setDocsError('');
    try {
      const candidates = docs.filter((doc) => doc.status === 'validated' && !doc.embedded);
      for (const doc of candidates) {
        await validateDocument(doc);
      }
      await loadDocuments();
    } catch (error) {
      setDocsError(error.message);
    } finally {
      setEmbeddingValidated(false);
    }
  };

  const validateSelected = async () => {
    const selectedDocs = docs.filter((doc) => selectedDocIds.has(doc.id) && !doc.embedded);
    if (selectedDocs.length === 0) return;
    setDocsError('');
    for (const doc of selectedDocs) {
      // Reuse existing validation/indexing workflow for each selected doc.
      // eslint-disable-next-line no-await-in-loop
      await validateDocument(doc);
    }
    setSelectedDocIds(new Set());
  };

  const rejectSelected = async () => {
    const selectedDocs = docs.filter((doc) => selectedDocIds.has(doc.id));
    if (selectedDocs.length === 0) return;
    setDocsError('');
    for (const doc of selectedDocs) {
      // eslint-disable-next-line no-await-in-loop
      await rejectDocument(doc);
    }
    setSelectedDocIds(new Set());
  };

  const sendAgent = async () => {
    if (!agentInput.trim()) return;
    const userText = agentInput.trim();
    setAgentMsgs((prev) => [...prev, { id: Date.now().toString(), role: 'user', content: userText, timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }]);
    setAgentInput('');
    setTyping(true);
    try {
      const normalized = userText.toLowerCase();
      let content = '';
      if (normalized.includes('embed validated')) {
        await embedAllValidated();
        content = 'Embedding triggered for validated non-embedded documents.';
      } else if (normalized.includes('refresh') || normalized.includes('status')) {
        await loadDocuments();
        content = `Documents loaded. total=${docs.length}, embedded=${docs.filter((d) => d.embedded).length}.`;
      } else {
        const history = agentMsgs.filter((m) => m.role === 'user' || m.role === 'assistant').map((m) => ({ role: m.role, content: m.content }));
        const response = await askGeneration({ query: userText, chatHistory: history });
        content = response.answer || 'No answer returned by generation service.';
      }
      setAgentMsgs((prev) => [...prev, { id: (Date.now() + 1).toString(), role: 'assistant', content, timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }]);
    } catch (error) {
      setAgentMsgs((prev) => [...prev, { id: (Date.now() + 1).toString(), role: 'assistant', content: `Request failed: ${error.message}`, timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }]);
    } finally {
      setTyping(false);
    }
  };

  const tabs = [
    { key: 'documents', label: 'Document Management', icon: FileText },
    { key: 'agent', label: 'Admin Agent Chat', icon: Bot },
  ];

  return (
    <AnimatedPage className="h-full flex flex-col">
      <div
        className="w-full h-full flex flex-col items-center relative"
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
      >
        {isDragging && (
          <div
            className="absolute inset-0 z-30 flex items-center justify-center"
            style={{
              background: 'rgba(12, 10, 22, 0.55)',
              border: '3px dashed #7c3aed',
              color: 'white',
              fontWeight: 600,
              letterSpacing: '0.2px',
              pointerEvents: 'none',
            }}
          >
            Drop documents anywhere under the navbar to upload
          </div>
        )}
        <input ref={fileInputRef} type="file" accept=".pdf,.txt,.md" multiple className="hidden" onChange={(event) => uploadFiles(event.target.files)} />

        <div className="flex gap-0 shrink-0 max-w-[1400px] mx-auto px-5 md:px-8" style={{ marginBottom: '24px' }}>
          {tabs.map(({ key, label, icon: Icon }) => (
            <button key={key} onClick={() => setTab(key)} className="flex items-center gap-2 px-6 text-sm font-medium transition-all" style={{ background: tab === key ? 'linear-gradient(135deg, #7c3aed, #06b6d4)' : 'var(--bg-secondary)', border: tab === key ? 'none' : '1px solid var(--border-color)', color: tab === key ? 'white' : 'var(--text-secondary)', boxShadow: tab === key ? '0 0 20px rgba(139,92,246,0.3)' : 'none', borderRadius: key === 'documents' ? '12px 0 0 50px' : '0 12px 50px 0', padding: '16px 24px', minHeight: '56px', display: 'flex', alignItems: 'center' }}>
              <Icon size={16} /> {label}
            </button>
          ))}
        </div>

        <div className="flex-1 w-screen flex justify-center" style={{ minHeight: 0 }}>
          <AnimatePresence mode="wait">
            {tab === 'documents' ? (
              <motion.div key="docs" className="h-full w-full flex justify-center relative" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                <div className="h-full w-full max-w-[1400px] flex flex-col px-5 md:px-8 mt-8 md:mt-12 overflow-auto" style={{ minHeight: 0 }}>

                  <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 shrink-0" style={{ marginTop: '24px', marginBottom: '16px' }}>
                    <div className="flex items-center gap-2 flex-1 w-full sm:w-auto px-4 rounded-xl transition-all input-glow" style={{ border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', minHeight: '48px' }}>
                      <Search size={16} style={{ color: 'var(--text-muted)' }} />
                      <input id="doc-search" type="text" placeholder="Search documents..." value={search} onChange={(e) => setSearch(e.target.value)} className="flex-1 bg-transparent outline-none text-sm" style={{ color: 'var(--text-primary)' }} />
                    </div>
                    <div className="flex items-center gap-2">
                      <select id="status-filter" value={filter} onChange={(e) => setFilter(e.target.value)} className="px-4 rounded-xl text-sm outline-none" style={{ border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', color: 'var(--text-primary)', minHeight: '48px', minWidth: '160px' }}>
                        <option value="all">All Status</option>
                        <option value="validated">Validated</option>
                        <option value="pending">Pending</option>
                        <option value="rejected">Rejected</option>
                      </select>
                      <motion.button onClick={loadDocuments} disabled={loadingDocs} className="flex items-center gap-2 px-6 rounded-xl text-sm font-medium" style={{ border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', color: 'var(--text-secondary)', minHeight: '48px', minWidth: '140px', justifyContent: 'center' }}>
                        <RefreshCw size={16} /> Refresh
                      </motion.button>
                      <motion.button onClick={() => fileInputRef.current?.click()} className="flex items-center gap-2 px-6 rounded-xl text-sm font-medium text-white" style={{ background: 'linear-gradient(135deg, #7c3aed, #06b6d4)', minHeight: '48px', minWidth: '140px', justifyContent: 'center' }}>
                        <Upload size={16} /> Upload
                      </motion.button>
                      <motion.button
                        onClick={validateSelected}
                        disabled={selectedDocIds.size === 0}
                        className="flex items-center gap-2 px-6 rounded-xl text-sm font-medium text-white disabled:opacity-50"
                        style={{ background: 'linear-gradient(135deg, #16a34a, #15803d)', minHeight: '48px', minWidth: '170px', justifyContent: 'center' }}
                      >
                        <Check size={16} /> Validate Selected
                      </motion.button>
                      <motion.button
                        onClick={rejectSelected}
                        disabled={selectedDocIds.size === 0}
                        className="flex items-center gap-2 px-6 rounded-xl text-sm font-medium text-white disabled:opacity-50"
                        style={{ background: 'linear-gradient(135deg, #dc2626, #b91c1c)', minHeight: '48px', minWidth: '170px', justifyContent: 'center' }}
                      >
                        <X size={16} /> Reject Selected
                      </motion.button>
                    </div>
                  </div>

                  {docsError && (
                    <div className="rounded-xl px-4 py-3 text-sm" style={{ background: 'rgba(239,68,68,0.08)', color: '#ef4444', border: '1px solid rgba(239,68,68,0.2)', marginBottom: '12px' }}>
                      {docsError}
                    </div>
                  )}

                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 shrink-0" style={{ marginBottom: '16px' }}>
                    {[
                      { l: 'Total', v: docs.length, color: 'var(--color-primary-400)' },
                      { l: 'Validated', v: docs.filter((d) => d.status === 'validated').length, color: '#10b981' },
                      { l: 'Pending', v: docs.filter((d) => d.status === 'pending').length, color: '#f59e0b' },
                      { l: 'Rejected', v: docs.filter((d) => d.status === 'rejected').length, color: '#ef4444' },
                    ].map((s, i) => (
                      <motion.div key={i} className="rounded-xl" style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', padding: '16px' }}>
                        <p className="text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>{s.l}</p>
                        <p className="text-2xl font-bold font-display" style={{ color: s.color }}>{s.v}</p>
                      </motion.div>
                    ))}
                  </div>

                  <div
                    className="overflow-auto rounded-xl"
                    style={{
                      border: '1px solid var(--border-color)',
                      marginTop: '16px',
                      minHeight: filtered.length === 0 ? '210px' : 'auto',
                      maxHeight: '58vh',
                    }}
                  >
                    <table className="w-full text-sm">
                      <thead>
                        <tr style={{ background: 'var(--bg-tertiary)', borderBottom: '1px solid var(--border-color)' }}>
                          <th className="px-3 py-4 text-center text-base font-semibold w-10" style={{ color: 'var(--text-secondary)' }}>
                            <input
                              type="checkbox"
                              checked={allFilteredSelected}
                              onChange={toggleSelectAllFiltered}
                              aria-label="Select all documents in current filter"
                            />
                          </th>
                          <th className="px-4 py-4 text-left text-base font-semibold" style={{ color: 'var(--text-secondary)' }}>Document</th>
                          <th className="px-4 py-4 text-left text-base font-semibold hidden md:table-cell" style={{ color: 'var(--text-secondary)' }}>Size</th>
                          <th className="px-4 py-4 text-left text-base font-semibold hidden sm:table-cell" style={{ color: 'var(--text-secondary)' }}>Date</th>
                          <th className="px-4 py-4 text-left text-base font-semibold" style={{ color: 'var(--text-secondary)' }}>Status</th>
                          <th className="px-4 py-4 text-center text-base font-semibold w-48" style={{ color: 'var(--text-secondary)' }}>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filtered.map((doc) => (
                          <motion.tr key={doc.id} className="transition-colors" style={{ borderBottom: '1px solid var(--border-color)', height: '76px' }}>
                            <td className="px-3 py-4 text-center align-middle">
                              <input
                                type="checkbox"
                                checked={selectedDocIds.has(doc.id)}
                                onChange={() => toggleDocSelection(doc.id)}
                                aria-label={`Select ${doc.name}`}
                              />
                            </td>
                            <td className="px-4 py-4 align-middle">
                              <div className="flex items-center gap-3">
                                <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0" style={{ background: 'rgba(139,92,246,0.08)' }}>
                                  <FileText size={14} style={{ color: 'var(--color-primary-400)' }} />
                                </div>
                                <div className="min-w-0">
                                  <div className="font-medium truncate max-w-50" style={{ color: 'var(--text-primary)' }}>{doc.name}</div>
                                  {doc.embedded && <div className="text-xs text-sky-400">Embedded</div>}
                                </div>
                              </div>
                            </td>
                            <td className="px-4 py-4 hidden md:table-cell align-middle" style={{ color: 'var(--text-secondary)' }}>{doc.size}</td>
                            <td className="px-4 py-4 hidden sm:table-cell align-middle" style={{ color: 'var(--text-secondary)' }}>{doc.date}</td>
                            <td className="px-4 py-4 align-middle"><StatusBadge status={doc.status} /></td>
                            <td className="px-4 py-4 w-48 align-middle">
                              <div className="grid grid-cols-4 justify-items-center items-center gap-2">
                                <button className="p-2.5 rounded-lg hover:bg-primary-500/10 transition-colors" title="View document" disabled={busyDocIds.has(doc.id)} onClick={() => viewDocument(doc)}><Eye size={18} /></button>
                                {doc.embedded ? (
                                  <>
                                    <span className="p-2.5 invisible"><Check size={18} /></span>
                                    <span className="p-2.5 invisible"><X size={18} /></span>
                                  </>
                                ) : (
                                  <>
                                    <button className="p-2.5 rounded-lg hover:bg-success/10 transition-colors" title="Validate and index if needed" disabled={busyDocIds.has(doc.id)} onClick={() => validateDocument(doc)}><Check size={18} /></button>
                                    <button className="p-2.5 rounded-lg hover:bg-warning/10 transition-colors" title="Reject" disabled={busyDocIds.has(doc.id)} onClick={() => rejectDocument(doc)}><X size={18} /></button>
                                  </>
                                )}
                                <button className="p-2.5 rounded-lg hover:bg-danger/10 text-danger transition-colors" title="Remove" disabled={busyDocIds.has(doc.id)} onClick={() => removeDocument(doc)}><Trash2 size={18} /></button>
                              </div>
                            </td>
                          </motion.tr>
                        ))}
                        {filtered.length === 0 && (
                          <>
                            <tr>
                              <td colSpan={6} className="px-4 py-3">&nbsp;</td>
                            </tr>
                            <tr>
                              <td colSpan={6} className="px-4 py-10 text-center" style={{ color: 'var(--text-muted)' }}>
                                <p className="text-lg font-semibold">
                                  {loadingDocs ? 'Loading documents...' : 'No documents found'}
                                </p>
                              </td>
                            </tr>
                          </>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </motion.div>
            ) : (
              <motion.div key="agent" className="h-full w-full flex justify-center" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                <div className="h-full w-full max-w-5xl flex flex-col px-5 md:px-8 relative md:left-20 lg:left-32 xl:left-40 mt-12 md:mt-16" style={{ minHeight: 0 }}>
                  <div className="flex-1 w-full" style={{ overflowY: 'auto', overflowX: 'hidden', scrollBehavior: 'smooth', minHeight: 0, scrollbarGutter: 'stable', paddingTop: '32px', paddingBottom: '32px' }}>
                    <div className="max-w-5xl" style={{ marginLeft: 'auto', marginRight: '0' }}>
                      {agentMsgs.map((msg) => (
                        <motion.div key={msg.id} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : ''}`} style={{ marginBottom: '32px' }} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
                          {msg.role === 'assistant' && <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mt-1" style={{ background: 'linear-gradient(135deg, #f59e0b, #ef4444)', boxShadow: '0 0 12px rgba(245,158,11,0.3)' }}><Bot size={15} className="text-white" /></div>}
                          <div className={`max-w-[80%] rounded-2xl ${msg.role === 'user' ? 'rounded-br-md' : 'rounded-bl-md'}`} style={msg.role === 'user' ? { background: 'linear-gradient(135deg, #7c3aed, #5b21b6)', color: 'white', boxShadow: '0 4px 15px rgba(139,92,246,0.2)', padding: '16px 24px' } : { background: 'var(--bg-tertiary)', color: 'var(--text-primary)', border: '1px solid var(--border-color)', padding: '16px 24px' }}>
                            <p className="text-sm leading-relaxed whitespace-pre-line my-2">{msg.content}</p>
                            <p className={`text-xs mt-2 ${msg.role === 'user' ? 'text-white/50' : ''}`} style={msg.role === 'assistant' ? { color: 'var(--text-muted)' } : {}}>{msg.timestamp}</p>
                          </div>
                          {msg.role === 'user' && <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mt-1" style={{ background: 'linear-gradient(135deg, #52525b, #27272a)' }}><User size={15} className="text-white" /></div>}
                        </motion.div>
                      ))}
                      {typing && <motion.div className="flex gap-3" initial={{ opacity: 0 }} animate={{ opacity: 1 }}><div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0" style={{ background: 'linear-gradient(135deg, #f59e0b, #ef4444)', boxShadow: '0 0 12px rgba(245,158,11,0.3)' }}><Bot size={15} className="text-white" /></div><div className="rounded-2xl rounded-bl-md" style={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-color)', padding: '16px 24px' }}><TypingIndicator /></div></motion.div>}
                      <div ref={endRef} />
                    </div>
                  </div>
                  <div className="py-3 w-full" style={{ borderColor: 'var(--border-color)', borderTop: '1px solid var(--border-color)' }}>
                    <div className="max-w-3xl mx-auto">
                      <div className="flex items-end gap-3 rounded-2xl p-6 transition-all input-glow" style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)' }}>
                        <textarea id="admin-agent-input" value={agentInput} onChange={(e) => setAgentInput(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendAgent(); } }} placeholder='Try: "refresh status" or "embed validated"' rows={3} className="flex-1 bg-transparent outline-none text-sm resize-none max-h-56" style={{ color: 'var(--text-primary)', padding: '16px 24px' }} />
                        <motion.button id="admin-send" onClick={sendAgent} disabled={!agentInput.trim() || typing} className="rounded-xl disabled:opacity-20 shrink-0" style={{ padding: '16px 22px', marginRight: '8px' }}>
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

        {previewOpen && (
          <div
            className="absolute inset-0 z-40 flex items-center justify-center"
            style={{ background: 'rgba(2, 6, 23, 0.65)' }}
            onClick={() => setPreviewOpen(false)}
          >
            <div
              className="w-[92%] max-w-5xl h-[86%] rounded-xl overflow-hidden"
              style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)' }}
              onClick={(event) => event.stopPropagation()}
            >
              <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: '1px solid var(--border-color)' }}>
                <p className="text-sm font-semibold truncate" style={{ color: 'var(--text-primary)' }}>
                  {previewName}
                </p>
                <div className="flex items-center gap-2">
                  <a href={previewUrl} target="_blank" rel="noreferrer" className="text-xs px-3 py-1 rounded-lg" style={{ border: '1px solid var(--border-color)', color: 'var(--text-secondary)' }}>
                    Open new tab
                  </a>
                  <button onClick={() => setPreviewOpen(false)} className="text-xs px-3 py-1 rounded-lg" style={{ border: '1px solid var(--border-color)', color: 'var(--text-secondary)' }}>
                    Close
                  </button>
                </div>
              </div>
              <div className="w-full h-[calc(100%-49px)]">
                {previewLoading ? (
                  <div className="w-full h-full flex items-center justify-center" style={{ color: 'var(--text-muted)' }}>
                    Loading preview...
                  </div>
                ) : (
                  <iframe title={`preview-${previewName}`} src={previewUrl} className="w-full h-full border-0" />
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </AnimatedPage>
  );
}
