import { useEffect, useMemo, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  FileText,
  Check,
  X,
  Clock,
  Search,
  Send,
  ChevronDown,
  Bot,
  User,
  Upload,
  Eye,
  Trash2,
  Ban,
} from 'lucide-react';
import AnimatedPage from '../components/AnimatedPage';
import TypingIndicator from '../components/TypingIndicator';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import {
  askGeneration,
  deleteDocumentRecord,
  deleteManagedUser,
  getDocumentSignedUrl,
  indexDocument,
  inviteUser,
  listDocuments,
  listManagedUsers,
  removeDocumentChunks,
  setUserBlock,
  setUserValidation,
  updateDocumentStatus,
  uploadDocument,
} from '../config/api';

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

function normalizeId(value) {
  return String(value || '').trim().toLowerCase();
}

function mapRow(row) {
  return {
    id: row.id,
    userId: row.user_id,
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
    <span
      className="inline-flex items-center gap-1.5 py-1 rounded-full text-xs font-medium"
      style={{ background: cfg.bg, color: cfg.text, border: `1px solid ${cfg.border}`, paddingLeft: '20px', paddingRight: '20px' }}
    >
      <Icon size={11} /> {cfg.label}
    </span>
  );
}

export default function AdminPage() {
  const { theme } = useTheme();
  const { supabase, user, getAccessToken } = useAuth();
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
      sources: [],
    },
  ]);
  const [agentInput, setAgentInput] = useState('');
  const [typing, setTyping] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewUrl, setPreviewUrl] = useState('');
  const [previewName, setPreviewName] = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);
  const [managedUsers, setManagedUsers] = useState([]);
  const [loadingManagedUsers, setLoadingManagedUsers] = useState(false);
  const [usersError, setUsersError] = useState('');
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviting, setInviting] = useState(false);
  const [inviteMessage, setInviteMessage] = useState('');
  const [busyUserIds, setBusyUserIds] = useState(new Set());
  const [userSearch, setUserSearch] = useState('');
  const [userFilter, setUserFilter] = useState('all');
  const dragDepthRef = useRef(0);
  const endRef = useRef(null);

  const managedUsersById = useMemo(
    () =>
      new Map(
        managedUsers.map((managedUser) => [normalizeId(managedUser.id), managedUser]),
      ),
    [managedUsers]
  );

  const getUploaderLabel = (userId) => {
    const normalizedUserId = normalizeId(userId);
    const managedUser = managedUsersById.get(normalizedUserId);
    if (!managedUser) return userId || 'Unknown uploader';
    return managedUser.username?.trim() || managedUser.email?.trim() || userId || 'Unknown uploader';
  };

  const markBusy = (docId, value) => {
    setBusyDocIds((prev) => {
      const next = new Set(prev);
      if (value) next.add(docId);
      else next.delete(docId);
      return next;
    });
  };

  const loadDocuments = async () => {
    if (!user) return;
    setLoadingDocs(true);
    setDocsError('');
    try {
      const token = await getAccessToken();
      const response = await listDocuments(token);
      const mapped = (response.documents || []).map(mapRow);
      setDocs(mapped);
      setSelectedDocIds((prev) => {
        const allowed = new Set(mapped.map((doc) => doc.id));
        return new Set([...prev].filter((id) => allowed.has(id)));
      });
    } catch (error) {
      setDocsError(error.message || 'Failed to load documents');
    } finally {
      setLoadingDocs(false);
    }
  };

  const markUserBusy = (userId, value) => {
    setBusyUserIds((prev) => {
      const next = new Set(prev);
      if (value) next.add(userId);
      else next.delete(userId);
      return next;
    });
  };

  const loadManagedUsersData = async () => {
    if (!user || user.user_metadata?.role !== 'admin') return;
    setLoadingManagedUsers(true);
    setUsersError('');
    try {
      const token = await getAccessToken();
      const response = await listManagedUsers(token);
      setManagedUsers(response.users || []);
    } catch (error) {
      setUsersError(error.message || 'Failed to load users');
    } finally {
      setLoadingManagedUsers(false);
    }
  };

  const handleInvite = async () => {
    if (!inviteEmail.trim()) return;
    setInviting(true);
    setInviteMessage('');
    setUsersError('');
    try {
      const token = await getAccessToken();
      const response = await inviteUser(token, {
        email: inviteEmail.trim(),
        role: 'user',
      });
      const deliveryNote = response.email_sent
        ? 'Invitation email sent.'
        : response.recovery_link
          ? `Email could not be sent. Share this recovery link: ${response.recovery_link}`
          : `Email could not be sent. Temporary password: ${response.generated_password}`;
      setInviteMessage(`${deliveryNote} ${response.message} for ${response.email}. User status remains invited until account setup is completed.`);
      setInviteEmail('');
      await loadManagedUsersData();
    } catch (error) {
      setUsersError(error.message || 'Failed to invite user');
    } finally {
      setInviting(false);
    }
  };

  const updateValidation = async (targetUser) => {
    markUserBusy(targetUser.id, true);
    setUsersError('');
    try {
      const token = await getAccessToken();
      await setUserValidation(token, targetUser.id, !targetUser.validated);
      await loadManagedUsersData();
    } catch (error) {
      setUsersError(error.message || 'Failed to update validation');
    } finally {
      markUserBusy(targetUser.id, false);
    }
  };

  const updateBlock = async (targetUser) => {
    markUserBusy(targetUser.id, true);
    setUsersError('');
    try {
      const token = await getAccessToken();
      await setUserBlock(token, targetUser.id, !targetUser.blocked);
      await loadManagedUsersData();
    } catch (error) {
      setUsersError(error.message || 'Failed to update block status');
    } finally {
      markUserBusy(targetUser.id, false);
    }
  };

  const validateAgain = async (targetUser) => {
    markUserBusy(targetUser.id, true);
    setUsersError('');
    try {
      const token = await getAccessToken();
      await setUserValidation(token, targetUser.id, true);
      await setUserBlock(token, targetUser.id, false);
      await loadManagedUsersData();
    } catch (error) {
      setUsersError(error.message || 'Failed to re-validate user');
    } finally {
      markUserBusy(targetUser.id, false);
    }
  };

  const deleteUser = async (targetUser) => {
    if (!window.confirm(`Delete user ${targetUser.email}? This cannot be undone.`)) return;
    markUserBusy(targetUser.id, true);
    setUsersError('');
    try {
      const token = await getAccessToken();
      await deleteManagedUser(token, targetUser.id);
      await loadManagedUsersData();
    } catch (error) {
      setUsersError(error.message || 'Failed to delete user');
    } finally {
      markUserBusy(targetUser.id, false);
    }
  };

  useEffect(() => {
    loadDocuments();
  }, [supabase, user]);

  useEffect(() => {
    if (!user || user.user_metadata?.role !== 'admin') return;
    loadManagedUsersData();
  }, [user?.id]);

  useEffect(() => {
    if (tab === 'users') {
      loadManagedUsersData();
    }
  }, [tab, user?.id]);

  useEffect(() => {
    if (!user || user.user_metadata?.role !== 'admin') return undefined;

    const intervalId = window.setInterval(() => {
      loadManagedUsersData();
    }, 10000);

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        loadManagedUsersData();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      window.clearInterval(intervalId);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [user?.id]);

  useEffect(() => {
    if (!supabase || !user?.id) return undefined;

    const channel = supabase
      .channel(`documents-realtime-${user.id}`)
      .on(
        'postgres_changes',
        {
          event: '*',
          schema: 'public',
          table: DOCS_TABLE,
        },
        () => {
          loadDocuments();
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [supabase, user?.id]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [agentMsgs, typing]);

  const docsWithUploader = useMemo(
    () =>
      docs.map((doc) => ({
        ...doc,
        uploaderLabel: getUploaderLabel(doc.userId),
      })),
    [docs, managedUsersById]
  );

  const filtered = useMemo(
    () =>
      docsWithUploader.filter(
        (doc) =>
          `${doc.name} ${doc.uploaderLabel}`.toLowerCase().includes(search.toLowerCase()) &&
          (filter === 'all' || doc.status === filter)
      ),
    [docsWithUploader, search, filter]
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
    if (!user || !files?.length) return;
    setDocsError('');
    try {
      const token = await getAccessToken();
      for (const file of files) {
        // eslint-disable-next-line no-await-in-loop
        await uploadDocument({ accessToken: token, userId: user.id, file });
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
    const token = await getAccessToken();
    const updated = await updateDocumentStatus(token, doc.id, { target_status: targetStatus });
    return updated.storage_path;
  };

  const indexValidatedDoc = async (docId) => {
    return indexDocument({
      document_id: docId,
      skip_if_embedded: true,
    });
  };

  const validateDocument = async (doc) => {
    markBusy(doc.id, true);
    setDocsError('');
    try {
      if (doc.status !== 'validated') {
        await moveDocument(doc, 'validated');
      }
      if (!doc.embedded) {
        await indexValidatedDoc(doc.id);
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
    markBusy(doc.id, true);
    setDocsError('');
    try {
      if (doc.embedded || doc.status === 'validated') {
        // Best effort vector cleanup before removing the Supabase document record.
        await removeDocumentChunks({ document_id: doc.id });
      }
      const token = await getAccessToken();
      await deleteDocumentRecord(token, doc.id);
      await loadDocuments();
    } catch (error) {
      setDocsError(error.message);
    } finally {
      markBusy(doc.id, false);
    }
  };

  const viewDocument = async (doc) => {
    markBusy(doc.id, true);
    setDocsError('');
    setPreviewLoading(true);
    try {
      const token = await getAccessToken();
      const data = await getDocumentSignedUrl(token, doc.id, 3600);
      setPreviewUrl(data.signed_url);
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
      let sources = [];
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
        sources = Array.isArray(response?.citations)
          ? [...new Set(response.citations.map((citation) => citation.document_name).filter(Boolean))]
          : [];
      }
      setAgentMsgs((prev) => [...prev, { id: (Date.now() + 1).toString(), role: 'assistant', content, timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }), sources }]);
    } catch (error) {
      setAgentMsgs((prev) => [...prev, { id: (Date.now() + 1).toString(), role: 'assistant', content: `Request failed: ${error.message}`, timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }), sources: [] }]);
    } finally {
      setTyping(false);
    }
  };

  const tabs = [
    { key: 'documents', label: 'Document Management', icon: FileText },
    { key: 'users', label: 'User Management', icon: User },
    { key: 'agent', label: 'Admin Agent Chat', icon: Bot },
  ];

  const getManagedUserStatus = (managedUser) => {
    if (managedUser.status) return managedUser.status;
    if (managedUser.blocked) return 'blocked';
    if (managedUser.invited) return 'invited';
    if (managedUser.validated) return 'validated';
    return 'pending';
  };

  const userStats = useMemo(() => ({
    total: managedUsers.length,
    validated: managedUsers.filter((managedUser) => getManagedUserStatus(managedUser) === 'validated').length,
    invited: managedUsers.filter((managedUser) => getManagedUserStatus(managedUser) === 'invited').length,
    pending: managedUsers.filter((managedUser) => getManagedUserStatus(managedUser) === 'pending').length,
    blocked: managedUsers.filter((managedUser) => managedUser.blocked).length,
  }), [managedUsers]);

  const filteredUsers = managedUsers.filter((managedUser) => {
    const status = getManagedUserStatus(managedUser);
    const query = userSearch.toLowerCase().trim();
    const matchesSearch = query === ''
      || (managedUser.email || '').toLowerCase().includes(query)
      || (managedUser.username || '').toLowerCase().includes(query)
      || (managedUser.phone_number || '').toLowerCase().includes(query);
    if (!matchesSearch) return false;
    if (userFilter === 'validated') return status === 'validated';
    if (userFilter === 'invited') return status === 'invited';
    if (userFilter === 'pending') return status === 'pending';
    if (userFilter === 'blocked') return status === 'blocked';
    return true;
  });

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
            <button key={key} onClick={() => setTab(key)} className="flex items-center gap-2 px-6 text-sm font-medium transition-all" style={{ background: tab === key ? 'linear-gradient(135deg, #7c3aed, #06b6d4)' : 'var(--bg-secondary)', border: tab === key ? 'none' : '1px solid var(--border-color)', color: tab === key ? 'white' : 'var(--text-secondary)', boxShadow: tab === key ? '0 0 20px rgba(139,92,246,0.3)' : 'none', borderRadius: key === 'documents' ? '12px 0 0 50px' : key === 'agent' ? '0 12px 50px 0' : '0', padding: '16px 24px', minHeight: '56px', display: 'flex', alignItems: 'center' }}>
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
                    <div className="flex items-center gap-2 flex-1 w-full sm:w-auto rounded-xl transition-all input-glow" style={{ border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', minHeight: '48px', paddingLeft: '24px', paddingRight: '24px' }}>
                      <Search size={16} style={{ color: 'var(--text-muted)' }} />
                      <input id="doc-search" type="text" placeholder="Search documents..." value={search} onChange={(e) => setSearch(e.target.value)} className="flex-1 bg-transparent outline-none text-sm" style={{ color: 'var(--text-primary)' }} />
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="relative">
                        <select
                          id="status-filter"
                          value={filter}
                          onChange={(e) => setFilter(e.target.value)}
                          className="rounded-xl text-sm outline-none appearance-none"
                          style={{ border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', color: 'var(--text-primary)', minHeight: '48px', minWidth: '200px', paddingLeft: '24px', paddingRight: '48px' }}
                        >
                          <option value="all">All Status</option>
                          <option value="validated">Validated</option>
                          <option value="pending">Pending</option>
                          <option value="rejected">Rejected</option>
                        </select>
                        <ChevronDown
                          size={16}
                          className="pointer-events-none absolute top-1/2 -translate-y-1/2"
                          style={{ right: '16px', color: 'var(--text-muted)' }}
                        />
                      </div>
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
                      <motion.div key={i} className="rounded-xl" style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', padding: '18px 30px' }}>
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
                        <tr className="sticky top-0 z-10" style={{ background: 'var(--bg-tertiary)', borderBottom: '1px solid var(--border-color)', minHeight: '62px' }}>
                          <th className="px-3 text-center text-base font-semibold w-10" style={{ color: 'var(--text-secondary)', paddingTop: '12px', paddingBottom: '12px' }}>
                            <input
                              type="checkbox"
                              checked={allFilteredSelected}
                              onChange={toggleSelectAllFiltered}
                              aria-label="Select all documents in current filter"
                            />
                          </th>
                          <th className="px-4 text-left text-base font-semibold" style={{ color: 'var(--text-secondary)', paddingTop: '12px', paddingBottom: '12px' }}>Document</th>
                          <th className="px-4 text-left text-base font-semibold hidden lg:table-cell" style={{ color: 'var(--text-secondary)', paddingTop: '12px', paddingBottom: '12px' }}>Uploader</th>
                          <th className="px-4 text-left text-base font-semibold hidden md:table-cell" style={{ color: 'var(--text-secondary)', paddingTop: '12px', paddingBottom: '12px' }}>Size</th>
                          <th className="px-4 text-left text-base font-semibold hidden sm:table-cell" style={{ color: 'var(--text-secondary)', paddingTop: '12px', paddingBottom: '12px' }}>Date</th>
                          <th className="px-4 text-left text-base font-semibold" style={{ color: 'var(--text-secondary)', paddingTop: '12px', paddingBottom: '12px' }}>Status</th>
                          <th className="px-4 text-center text-base font-semibold w-48" style={{ color: 'var(--text-secondary)', paddingTop: '12px', paddingBottom: '12px' }}>Actions</th>
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
                            <td className="px-4 py-4 hidden lg:table-cell align-middle" style={{ color: 'var(--text-secondary)' }}>
                              {doc.uploaderLabel}
                            </td>
                            <td className="px-4 py-4 hidden md:table-cell align-middle" style={{ color: 'var(--text-secondary)' }}>{doc.size}</td>
                            <td className="px-4 py-4 hidden sm:table-cell align-middle" style={{ color: 'var(--text-secondary)' }}>{doc.date}</td>
                            <td className="px-4 py-4 align-middle"><StatusBadge status={doc.status} /></td>
                            <td className="px-4 py-4 w-48 align-middle">
                              <div className="grid grid-cols-4 justify-items-center items-center gap-2">
                                <button className="p-2.5 rounded-lg hover:bg-primary-500/10 transition-colors" style={{ color: theme === 'dark' ? '#ffffff' : 'var(--text-secondary)' }} title="View document" disabled={busyDocIds.has(doc.id)} onClick={() => viewDocument(doc)}><Eye size={18} /></button>
                                {doc.embedded || doc.status !== 'pending' || busyDocIds.has(doc.id) ? (
                                  <>
                                    <span className="p-2.5 invisible"><Check size={18} /></span>
                                    <span className="p-2.5 invisible"><X size={18} /></span>
                                  </>
                                ) : (
                                  <>
                                    <button className="p-2.5 rounded-lg hover:bg-success/10 transition-colors" style={{ color: theme === 'dark' ? '#ffffff' : 'var(--text-secondary)' }} title="Validate and index if needed" disabled={busyDocIds.has(doc.id)} onClick={() => validateDocument(doc)}><Check size={18} /></button>
                                    <button className="p-2.5 rounded-lg hover:bg-warning/10 transition-colors" style={{ color: theme === 'dark' ? '#ffffff' : 'var(--text-secondary)' }} title="Reject" disabled={busyDocIds.has(doc.id)} onClick={() => rejectDocument(doc)}><X size={18} /></button>
                                  </>
                                )}
                                <button className="p-2.5 rounded-lg hover:bg-danger/10 transition-colors" style={{ color: '#ef4444' }} title="Remove" disabled={busyDocIds.has(doc.id)} onClick={() => removeDocument(doc)}><Trash2 size={18} /></button>
                              </div>
                            </td>
                          </motion.tr>
                        ))}
                        {filtered.length === 0 && (
                          <>
                            <tr>
                              <td colSpan={7} className="px-4 py-3">&nbsp;</td>
                            </tr>
                            <tr>
                              <td colSpan={7} className="px-4 py-10 text-center" style={{ color: 'var(--text-muted)' }}>
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
            ) : tab === 'users' ? (
              <motion.div key="users" className="h-full w-full flex justify-center relative" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                <div className="h-full w-full max-w-[1400px] flex flex-col px-5 md:px-8 mt-8 md:mt-12 overflow-auto" style={{ minHeight: 0 }}>
                  <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 shrink-0" style={{ marginBottom: '16px' }}>
                    <div className="flex-1 w-full sm:w-auto flex items-center gap-2 rounded-xl transition-all input-glow" style={{ border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', minHeight: '48px', paddingLeft: '24px', paddingRight: '24px' }}>
                      <Search size={16} style={{ color: 'var(--text-muted)' }} />
                      <input
                        type="text"
                        placeholder="Search users by email..."
                        value={userSearch}
                        onChange={(event) => setUserSearch(event.target.value)}
                        className="flex-1 bg-transparent outline-none text-sm"
                        style={{ color: 'var(--text-primary)' }}
                      />
                    </div>
                    <div className="relative w-full sm:w-auto">
                      <select
                        id="user-status-filter"
                        value={userFilter}
                        onChange={(event) => setUserFilter(event.target.value)}
                        className="rounded-xl text-sm outline-none appearance-none"
                        style={{ border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', color: 'var(--text-primary)', minHeight: '48px', minWidth: '200px', width: '100%', paddingLeft: '24px', paddingRight: '48px' }}
                        >
                          <option value="all">All Users</option>
                          <option value="validated">Validated</option>
                          <option value="invited">Invited</option>
                          <option value="pending">Pending</option>
                          <option value="blocked">Blocked</option>
                        </select>
                      <ChevronDown
                        size={16}
                        className="pointer-events-none absolute top-1/2 -translate-y-1/2"
                        style={{ right: '16px', color: 'var(--text-muted)' }}
                      />
                    </div>
                    <div className="flex items-center gap-2 w-full sm:w-auto">
                      <input
                        type="email"
                        placeholder="Invite user email"
                        value={inviteEmail}
                        onChange={(event) => setInviteEmail(event.target.value)}
                        className="rounded-xl text-sm outline-none"
                        style={{ border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', color: 'var(--text-primary)', minHeight: '48px', minWidth: '260px', width: '100%', paddingLeft: '20px', paddingRight: '20px' }}
                      />
                      <motion.button
                        onClick={handleInvite}
                        disabled={inviting || !inviteEmail.trim()}
                        className="flex items-center gap-2 px-6 rounded-xl text-sm font-medium text-white disabled:opacity-50"
                        style={{ background: 'linear-gradient(135deg, #7c3aed, #06b6d4)', minHeight: '48px', minWidth: '140px', justifyContent: 'center' }}
                      >
                        {inviting ? 'Inviting...' : 'Invite User'}
                      </motion.button>
                    </div>
                  </div>

                  {(usersError || inviteMessage) && (
                    <div className="rounded-xl px-4 py-3 text-sm" style={{ background: usersError ? 'rgba(239,68,68,0.08)' : 'rgba(16,185,129,0.08)', color: usersError ? '#ef4444' : '#10b981', border: usersError ? '1px solid rgba(239,68,68,0.2)' : '1px solid rgba(16,185,129,0.2)', marginBottom: '12px' }}>
                      {usersError || inviteMessage}
                    </div>
                  )}

                  <div className="grid grid-cols-2 md:grid-cols-5 gap-3 shrink-0" style={{ marginBottom: '16px' }}>
                    {[
                      { l: 'Total', v: userStats.total, color: 'var(--color-primary-400)' },
                      { l: 'Validated', v: userStats.validated, color: '#10b981' },
                      { l: 'Invited', v: userStats.invited, color: '#38bdf8' },
                      { l: 'Pending', v: userStats.pending, color: '#f59e0b' },
                      { l: 'Blocked', v: userStats.blocked, color: '#ef4444' },
                    ].map((s, i) => (
                      <motion.div key={i} className="rounded-xl" style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', padding: '18px 30px' }}>
                        <p className="text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>{s.l}</p>
                        <p className="text-2xl font-bold font-display" style={{ color: s.color }}>{s.v}</p>
                      </motion.div>
                    ))}
                  </div>

                  <div className="overflow-auto rounded-xl" style={{ border: '1px solid var(--border-color)', marginTop: '16px', minHeight: filteredUsers.length === 0 ? '210px' : 'auto', maxHeight: '58vh' }}>
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="sticky top-0 z-10" style={{ background: 'var(--bg-tertiary)', borderBottom: '1px solid var(--border-color)', minHeight: '62px' }}>
                          <th className="text-left text-base font-semibold" style={{ color: 'var(--text-secondary)', paddingTop: '12px', paddingBottom: '12px', paddingLeft: '28px', paddingRight: '16px' }}>User Info</th>
                          <th className="px-4 text-left text-base font-semibold hidden md:table-cell" style={{ color: 'var(--text-secondary)', paddingTop: '12px', paddingBottom: '12px' }}>Role</th>
                          <th className="px-4 text-left text-base font-semibold" style={{ color: 'var(--text-secondary)', paddingTop: '12px', paddingBottom: '12px' }}>Status</th>
                          <th className="px-4 text-center text-base font-semibold w-40" style={{ color: 'var(--text-secondary)', paddingTop: '12px', paddingBottom: '12px' }}>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredUsers.map((managedUser) => {
                          const status = getManagedUserStatus(managedUser);
                          const statusCfg = status === 'validated'
                            ? { bg: 'rgba(16,185,129,0.1)', color: '#10b981', border: '1px solid rgba(16,185,129,0.2)', label: 'Validated' }
                            : status === 'invited'
                              ? { bg: 'rgba(56,189,248,0.12)', color: '#38bdf8', border: '1px solid rgba(56,189,248,0.25)', label: 'Invited' }
                            : status === 'blocked'
                              ? { bg: 'rgba(239,68,68,0.1)', color: '#ef4444', border: '1px solid rgba(239,68,68,0.2)', label: 'Blocked' }
                              : { bg: 'rgba(245,158,11,0.1)', color: '#f59e0b', border: '1px solid rgba(245,158,11,0.2)', label: 'Pending' };
                          return (
                          <tr key={managedUser.id} className="transition-colors" style={{ borderBottom: '1px solid var(--border-color)', height: '76px' }}>
                            <td className="py-4 align-middle" style={{ paddingLeft: '28px', paddingRight: '16px' }}>
                              <div className="flex items-center gap-3 min-w-0" style={{ paddingLeft: '4px' }}>
                                <div className="w-9 h-9 rounded-full overflow-hidden flex items-center justify-center shrink-0" style={{ background: 'rgba(139,92,246,0.1)', border: '1px solid var(--border-color)' }}>
                                  {managedUser.profile_picture ? (
                                    <img src={managedUser.profile_picture} alt="Profile" className="w-full h-full object-cover" />
                                  ) : (
                                    <User size={14} style={{ color: 'var(--text-muted)' }} />
                                  )}
                                </div>
                                <div className="min-w-0">
                                  <div className="font-medium truncate max-w-[360px]" style={{ color: 'var(--text-primary)' }}>
                                    {managedUser.username || 'No username'}
                                  </div>
                                  <div className="text-xs truncate max-w-[360px]" style={{ color: 'var(--text-muted)' }}>
                                    {managedUser.email}
                                  </div>
                                  <div className="text-xs truncate max-w-[360px]" style={{ color: 'var(--text-muted)' }}>
                                    {managedUser.phone_number || 'No phone'}
                                  </div>
                                </div>
                              </div>
                            </td>
                            <td className="px-4 py-4 hidden md:table-cell align-middle" style={{ color: 'var(--text-secondary)' }}>{managedUser.role}</td>
                            <td className="px-4 py-4 align-middle">
                              <span className="inline-flex items-center py-1 rounded-full text-xs font-medium" style={{ background: statusCfg.bg, color: statusCfg.color, border: statusCfg.border, paddingLeft: '14px', paddingRight: '14px' }}>
                                {statusCfg.label}
                              </span>
                            </td>
                            <td className="px-4 py-4 align-middle w-40">
                              <div className="grid grid-cols-3 justify-items-center items-center gap-2">
                                {status !== 'validated' && status !== 'invited' ? (
                                  <button
                                    onClick={() => (status === 'blocked' ? validateAgain(managedUser) : updateValidation(managedUser))}
                                    disabled={busyUserIds.has(managedUser.id) || managedUser.role === 'admin'}
                                    className="p-2.5 rounded-lg hover:bg-success/10 transition-colors disabled:opacity-50"
                                    style={{ color: theme === 'dark' ? '#ffffff' : 'var(--text-secondary)' }}
                                    title={status === 'blocked' ? 'Validate again' : 'Validate user'}
                                  >
                                    <Check size={18} />
                                  </button>
                                ) : (
                                  <span className="p-2.5 invisible"><Check size={18} /></span>
                                )}
                                {status !== 'blocked' ? (
                                  <button
                                    onClick={() => updateBlock(managedUser)}
                                    disabled={busyUserIds.has(managedUser.id) || managedUser.role === 'admin'}
                                    className="p-2.5 rounded-lg hover:bg-warning/10 transition-colors disabled:opacity-50"
                                    style={{ color: theme === 'dark' ? '#ffffff' : 'var(--text-secondary)' }}
                                    title="Block user"
                                  >
                                    <Ban size={18} />
                                  </button>
                                ) : (
                                  <span className="p-2.5 invisible"><Ban size={18} /></span>
                                )}
                                <button
                                  onClick={() => deleteUser(managedUser)}
                                  disabled={busyUserIds.has(managedUser.id) || managedUser.role === 'admin' || managedUser.id === user?.id}
                                  className="p-2.5 rounded-lg hover:bg-danger/10 transition-colors disabled:opacity-50"
                                  style={{ color: '#ef4444' }}
                                  title="Delete user"
                                >
                                  <Trash2 size={18} />
                                </button>
                              </div>
                            </td>
                          </tr>
                        )})}
                        {filteredUsers.length === 0 && (
                          <>
                            <tr>
                              <td colSpan={4} className="px-4 py-3">&nbsp;</td>
                            </tr>
                            <tr>
                              <td colSpan={4} className="px-4 py-10 text-center" style={{ color: 'var(--text-muted)' }}>
                                <p className="text-lg font-semibold">
                                  {loadingManagedUsers ? 'Loading users...' : 'No users found'}
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
                <div className="h-full w-full max-w-5xl flex flex-col px-5 md:px-8 mt-12 md:mt-16" style={{ minHeight: 0 }}>
                  <div className="flex-1 w-full" style={{ overflowY: 'auto', overflowX: 'hidden', scrollBehavior: 'smooth', minHeight: 0, scrollbarGutter: 'stable', paddingTop: '32px', paddingBottom: '32px' }}>
                    <div className="max-w-5xl md:-ml-24 lg:-ml-32 xl:-ml-40" style={{ marginLeft: '0', marginRight: 'auto' }}>
                      {agentMsgs.map((msg) => (
                        <motion.div key={msg.id} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : ''}`} style={{ marginBottom: '32px' }} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
                          {msg.role === 'assistant' && <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mt-1" style={{ background: 'linear-gradient(135deg, #f59e0b, #ef4444)', boxShadow: '0 0 12px rgba(245,158,11,0.3)' }}><Bot size={15} className="text-white" /></div>}
                          <div className={`max-w-[80%] rounded-2xl ${msg.role === 'user' ? 'rounded-br-md' : 'rounded-bl-md'}`} style={msg.role === 'user' ? { background: 'linear-gradient(135deg, #7c3aed, #5b21b6)', color: 'white', boxShadow: '0 4px 15px rgba(139,92,246,0.2)', padding: '16px 24px' } : { background: 'var(--bg-tertiary)', color: 'var(--text-primary)', border: '1px solid var(--border-color)', padding: '16px 24px' }}>
                            <p className="text-sm leading-relaxed whitespace-pre-line my-2">{msg.content}</p>
                            {msg.sources && msg.sources.length > 0 && (
                              <div className="mt-3 pt-3" style={{ borderTop: '1px solid var(--border-color)' }}>
                                <p className="text-xs font-medium mb-1.5" style={{ color: 'var(--text-muted)' }}>Sources:</p>
                                <div className="flex flex-wrap gap-1.5">
                                  {msg.sources.map((src, i) => (
                                    <span key={i} className="text-xs px-2.5 py-0.5 rounded-full" style={{ background: 'rgba(139,92,246,0.08)', color: 'var(--color-primary-400)', border: '1px solid rgba(139,92,246,0.15)' }}>
                                      {src}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            )}
                            <p className={`text-xs mt-2 ${msg.role === 'user' ? 'text-white/50' : ''}`} style={msg.role === 'assistant' ? { color: 'var(--text-muted)' } : {}}>{msg.timestamp}</p>
                          </div>
                          {msg.role === 'user' && <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mt-1" style={{ background: 'linear-gradient(135deg, #52525b, #27272a)' }}><User size={15} className="text-white" /></div>}
                        </motion.div>
                      ))}
                      {typing && <motion.div className="flex gap-3" initial={{ opacity: 0 }} animate={{ opacity: 1 }}><div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0" style={{ background: 'linear-gradient(135deg, #f59e0b, #ef4444)', boxShadow: '0 0 12px rgba(245,158,11,0.3)' }}><Bot size={15} className="text-white" /></div><div className="rounded-2xl rounded-bl-md" style={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-color)', padding: '16px 24px' }}><TypingIndicator /></div></motion.div>}
                      <div ref={endRef} />
                    </div>
                  </div>
                  <div className="py-3 w-full" style={{ transform: 'translateY(-14px)' }}>
                    <div className="max-w-5xl md:-ml-24 lg:-ml-32 xl:-ml-40" style={{ marginLeft: '0', marginRight: 'auto' }}>
                      <div className="w-full" style={{ paddingLeft: '44px', paddingRight: '44px' }}>
                        <div className="flex items-end gap-3 rounded-2xl p-6 transition-all input-glow" style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)' }}>
                          <textarea id="admin-agent-input" value={agentInput} onChange={(e) => setAgentInput(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendAgent(); } }} placeholder='Try: "refresh status" or "embed validated"' rows={3} className="flex-1 bg-transparent outline-none text-sm resize-none max-h-56" style={{ color: 'var(--text-primary)', padding: '16px 24px' }} />
                          <motion.button id="admin-send" onClick={sendAgent} disabled={!agentInput.trim() || typing} className="rounded-xl disabled:opacity-20 shrink-0" style={{ padding: '16px 22px', marginRight: '8px' }}>
                            <Send size={16} color={agentInput.trim() && !typing ? '#7c3aed' : (theme === 'dark' ? 'white' : 'black')} />
                          </motion.button>
                        </div>
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
