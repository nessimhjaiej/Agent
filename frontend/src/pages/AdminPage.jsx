import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
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
  AlertTriangle,
} from 'lucide-react';
import AnimatedPage from '../components/AnimatedPage';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import {
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
  streamAdmin,
  updateDocumentStatus,
  uploadDocument,
} from '../config/api';

const DOCS_TABLE = import.meta.env.VITE_SUPABASE_DOCS_TABLE || 'documents';
const ADMIN_AGENT_WARNING =
  'Admin actions can change live data and system behavior. You are responsible for reviewing every suggestion, confirming only changes you understand, and accepting the outcome of any update you choose to apply.';
const MESSAGE_TYPING_INTERVAL_MS = 38;

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

function extractAdminStreamResponse(event) {
  if (!event || typeof event !== 'object') return null;
  if (event.type === 'response' && event.data && typeof event.data === 'object') {
    return event.data;
  }
  if (event.type === 'final' && event.response && typeof event.response === 'object') {
    return event.response;
  }
  return null;
}

function formatActivityLine(activity) {
  if (!activity || typeof activity !== 'object') return '';
  const title = typeof activity.title === 'string' ? activity.title.trim() : '';
  const detail = typeof activity.detail === 'string' ? activity.detail.trim() : '';
  if (title && detail) return `${title}: ${detail}`;
  return title || detail || '';
}

function buildAdminGreeting(currentUser) {
  const username = currentUser?.user_metadata?.username?.trim()
    || currentUser?.user_metadata?.full_name?.trim()
    || currentUser?.email?.split('@')[0]?.trim()
    || '';

  return username
    ? `Hello ${username}, how can I help you today?`
    : 'Hello, how can I help you today?';
}

function AnimatedAssistantText({ text, animate }) {
  const [visibleLength, setVisibleLength] = useState(animate ? 0 : text.length);
  const previousTextRef = useRef(text);

  useEffect(() => {
    if (!animate) {
      setVisibleLength(text.length);
      previousTextRef.current = text;
      return;
    }

    const previousText = previousTextRef.current;
    previousTextRef.current = text;

    if (text !== previousText && !text.startsWith(previousText)) {
      setVisibleLength(0);
    }
  }, [animate, text]);

  useEffect(() => {
    if (!animate || visibleLength >= text.length) return undefined;

    const timer = window.setTimeout(() => {
      setVisibleLength((current) => {
        const remaining = text.length - current;
        const nextStep = remaining > 24 ? 3 : remaining > 12 ? 2 : 1;
        return Math.min(text.length, current + nextStep);
      });
    }, MESSAGE_TYPING_INTERVAL_MS);

    return () => window.clearTimeout(timer);
  }, [animate, text, visibleLength]);

  const renderedText = animate ? text.slice(0, visibleLength) : text;

  return (
    <span>
      {renderedText}
      {animate && (
        <motion.span
          aria-hidden="true"
          className="inline-block align-middle"
          style={{
            width: '0.45em',
            height: '1.05em',
            marginLeft: '2px',
            borderRadius: '999px',
            background: 'currentColor',
          }}
          animate={{ opacity: [0.2, 1, 0.2] }}
          transition={{ duration: 0.9, repeat: Infinity, ease: 'easeInOut' }}
        />
      )}
    </span>
  );
}

function renderInlineMarkdown(text, keyPrefix = 'md-inline') {
  const chunks = String(text || '').split(/(`[^`]+`|\*\*[^*]+\*\*)/g).filter(Boolean);
  return chunks.map((chunk, index) => {
    const key = `${keyPrefix}-${index}`;
    if (chunk.startsWith('`') && chunk.endsWith('`') && chunk.length >= 2) {
      return (
        <code
          key={key}
          style={{
            background: 'rgba(148,163,184,0.18)',
            border: '1px solid rgba(148,163,184,0.25)',
            borderRadius: '6px',
            padding: '1px 6px',
            fontSize: '0.92em',
          }}
        >
          {chunk.slice(1, -1)}
        </code>
      );
    }
    if (chunk.startsWith('**') && chunk.endsWith('**') && chunk.length >= 4) {
      return <strong key={key}>{chunk.slice(2, -2)}</strong>;
    }
    return <span key={key}>{chunk}</span>;
  });
}

function MarkdownLite({ text }) {
  const lines = String(text || '').split('\n');
  const blocks = [];
  let listItems = [];
  let paragraphLines = [];

  const flushList = () => {
    if (listItems.length === 0) return;
    const items = listItems;
    listItems = [];
    blocks.push(
      <ul key={`md-ul-${blocks.length}`} style={{ margin: '10px 0 12px 20px', listStyle: 'disc' }}>
        {items.map((item, index) => (
          <li key={`md-li-${blocks.length}-${index}`} style={{ marginBottom: '6px' }}>
            {renderInlineMarkdown(item, `md-li-inline-${blocks.length}-${index}`)}
          </li>
        ))}
      </ul>
    );
  };

  const flushParagraph = () => {
    if (paragraphLines.length === 0) return;
    const content = paragraphLines.join(' ');
    paragraphLines = [];
    blocks.push(
      <p key={`md-p-${blocks.length}`} style={{ margin: '8px 0 12px' }}>
        {renderInlineMarkdown(content, `md-p-inline-${blocks.length}`)}
      </p>
    );
  };

  lines.forEach((rawLine) => {
    const line = rawLine.trimEnd();
    const trimmed = line.trim();
    if (!trimmed) {
      flushList();
      flushParagraph();
      return;
    }
    if (trimmed.startsWith('### ')) {
      flushList();
      flushParagraph();
      blocks.push(
        <h3 key={`md-h3-${blocks.length}`} style={{ margin: '14px 0 8px', fontSize: '15px', fontWeight: 700 }}>
          {renderInlineMarkdown(trimmed.slice(4), `md-h3-inline-${blocks.length}`)}
        </h3>
      );
      return;
    }
    if (trimmed.startsWith('## ')) {
      flushList();
      flushParagraph();
      blocks.push(
        <h2 key={`md-h2-${blocks.length}`} style={{ margin: '16px 0 10px', fontSize: '17px', fontWeight: 800 }}>
          {renderInlineMarkdown(trimmed.slice(3), `md-h2-inline-${blocks.length}`)}
        </h2>
      );
      return;
    }
    if (trimmed.startsWith('# ')) {
      flushList();
      flushParagraph();
      blocks.push(
        <h1 key={`md-h1-${blocks.length}`} style={{ margin: '18px 0 10px', fontSize: '19px', fontWeight: 800 }}>
          {renderInlineMarkdown(trimmed.slice(2), `md-h1-inline-${blocks.length}`)}
        </h1>
      );
      return;
    }
    if (trimmed.startsWith('- ')) {
      flushParagraph();
      listItems.push(trimmed.slice(2).trim());
      return;
    }
    flushList();
    paragraphLines.push(trimmed);
  });

  flushList();
  flushParagraph();

  if (blocks.length === 0) {
    return <p style={{ margin: '8px 0 12px' }}>{text}</p>;
  }
  return <div>{blocks}</div>;
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
      content: buildAdminGreeting(user),
      sources: [],
      detailsOpen: false,
      activity: [],
      isStreaming: false,
    },
  ]);
  const [agentInput, setAgentInput] = useState('');
  const [typing, setTyping] = useState(false);
  const [agentSessionId, setAgentSessionId] = useState(null);
  const [agentPendingAction, setAgentPendingAction] = useState(null);
  const [agentWarningConfirmed, setAgentWarningConfirmed] = useState(false);
  const [showAgentWarningModal, setShowAgentWarningModal] = useState(false);
  const [hoveredWarningButton, setHoveredWarningButton] = useState(null);
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

  const appendAssistantPlaceholder = (messageId) => {
    setAgentMsgs((prev) => [
      ...prev,
      {
        id: messageId,
        role: 'assistant',
        content: '',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        sources: [],
        activity: [],
        detailsOpen: false,
        isStreaming: true,
      },
    ]);
  };

  const resumeAssistantStreaming = (messageId) => {
    setAgentMsgs((prev) =>
      prev.map((msg) => (
        msg.id === messageId
          ? { ...msg, isStreaming: true }
          : msg
      ))
    );
  };

  const updateAssistantPlaceholder = (messageId, updater) => {
    setAgentMsgs((prev) =>
      prev.map((msg) => {
        if (msg.id !== messageId) return msg;
        const patch = updater(msg) || {};
        return { ...msg, ...patch };
      })
    );
  };

  const mergeActivityItems = (existingItems = [], nextItems = []) => {
    const merged = [];
    const seen = new Set();

    [...existingItems, ...nextItems].forEach((item) => {
      if (!item || typeof item !== 'object') return;
      const key = JSON.stringify(item);
      if (seen.has(key)) return;
      seen.add(key);
      merged.push(item);
    });

    return merged;
  };

  const finishAssistantStreaming = (messageId, finalText = '') => {
    const estimatedDelay = Math.max(
      260,
      Math.min(1800, Math.ceil((finalText.length || 0) / 2) * MESSAGE_TYPING_INTERVAL_MS)
    );

    window.setTimeout(() => {
      updateAssistantPlaceholder(messageId, () => ({
        isStreaming: false,
      }));
    }, estimatedDelay);
  };

  const toggleAssistantDetails = (messageId) => {
    setAgentMsgs((prev) =>
      prev.map((msg) => (
        msg.id === messageId
          ? { ...msg, detailsOpen: !msg.detailsOpen }
          : msg
      ))
    );
  };

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
      if (response.message === 'User promoted to admin') {
        setInviteMessage(`${response.email} turned into an admin.`);
      } else {
        const deliveryNote = response.email_sent
          ? 'Invitation email sent.'
          : response.recovery_link
            ? `Email could not be sent. Share this recovery link: ${response.recovery_link}`
            : `Email could not be sent. Temporary password: ${response.generated_password}`;
        setInviteMessage(`${deliveryNote} ${response.message} for ${response.email}. User status remains invited until account setup is completed.`);
      }
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
    setAgentWarningConfirmed(false);
    setShowAgentWarningModal(tab === 'agent');
  }, [user?.id]);

  useEffect(() => {
    setAgentMsgs((prev) => {
      if (prev.length !== 1 || prev[0]?.id !== '0' || prev[0]?.role !== 'assistant') {
        return prev;
      }

      const greeting = buildAdminGreeting(user);
      if (prev[0].content === greeting) return prev;

      return [
        {
          ...prev[0],
          content: greeting,
        },
      ];
    });
  }, [user?.id, user?.email, user?.user_metadata?.username, user?.user_metadata?.full_name]);

  useEffect(() => {
    if (tab === 'agent' && !agentWarningConfirmed) {
      setShowAgentWarningModal(true);
    }
  }, [tab, agentWarningConfirmed]);

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
    const assistantMessageId = `${Date.now()}-assistant`;
    let finalDisplayText = '';
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
        appendAssistantPlaceholder(assistantMessageId);
        const accessToken = await getAccessToken();
        let finalResponse = null;
        await streamAdmin(
          {
            message: userText,
            session_id: agentSessionId,
            selected_mode: 'qa',
            access_token: accessToken,
          },
          (event) => {
            if (event.session_id) {
              setAgentSessionId(event.session_id);
            }
            if (event.type === 'status') {
              finalDisplayText = 'Working on your request...';
              updateAssistantPlaceholder(assistantMessageId, () => ({
                content: finalDisplayText,
              }));
            }
            if (event.type === 'activity') {
              const activityText = formatActivityLine(event.data) || 'Working on your request...';
              finalDisplayText = activityText;
              updateAssistantPlaceholder(assistantMessageId, (msg) => ({
                content: activityText,
                activity: [...(Array.isArray(msg.activity) ? msg.activity : []), event.data],
              }));
            }
            if (event.type === 'confirmation') {
              setAgentPendingAction(event.data);
            }
            if (event.type === 'error') {
              finalDisplayText = `Request failed: ${event.message || 'Unknown admin-service error'}`;
              updateAssistantPlaceholder(assistantMessageId, () => ({
                content: finalDisplayText,
              }));
            }
            const resolvedResponse = extractAdminStreamResponse(event);
            if (resolvedResponse) {
              finalResponse = resolvedResponse;
              finalDisplayText = resolvedResponse.answer || finalDisplayText || 'No answer returned by admin service.';
              updateAssistantPlaceholder(assistantMessageId, (msg) => ({
                content: resolvedResponse.answer || msg.content || 'No answer returned by admin service.',
                sources: Array.isArray(resolvedResponse.citations)
                  ? [...new Set(resolvedResponse.citations.map((citation) => citation.document_name).filter(Boolean))]
                  : [],
                activity: mergeActivityItems(
                  Array.isArray(msg.activity) ? msg.activity : [],
                  Array.isArray(resolvedResponse.activity) ? resolvedResponse.activity : [],
                ),
              }));
            }
          }
        );
        content = finalResponse?.answer || 'No answer returned by admin service.';
        finalDisplayText = content;
        sources = Array.isArray(finalResponse?.citations)
          ? [...new Set(finalResponse.citations.map((citation) => citation.document_name).filter(Boolean))]
          : [];
        setAgentPendingAction(finalResponse?.pending_action || null);
        updateAssistantPlaceholder(assistantMessageId, (msg) => ({
          content,
          sources,
          activity: Array.isArray(finalResponse?.activity) && finalResponse.activity.length > 0
            ? finalResponse.activity
            : (Array.isArray(msg.activity) ? msg.activity : []),
        }));
      }
      if (normalized.includes('embed validated') || normalized.includes('refresh') || normalized.includes('status')) {
        setAgentMsgs((prev) => [...prev, { id: (Date.now() + 1).toString(), role: 'assistant', content, timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }), sources, activity: [], detailsOpen: false, isStreaming: false }]);
      }
    } catch (error) {
      finalDisplayText = `Request failed: ${error.message}`;
      updateAssistantPlaceholder(assistantMessageId, () => ({
        content: finalDisplayText,
        activity: [],
      }));
    } finally {
      finishAssistantStreaming(assistantMessageId, finalDisplayText);
      setTyping(false);
    }
  };

  const confirmAgentAction = async () => {
    if (!agentPendingAction || typing) return;
    setTyping(true);
    const lastAssistantMessage = [...agentMsgs].reverse().find((msg) => msg.role === 'assistant');
    const assistantMessageId = lastAssistantMessage?.id || `${Date.now()}-confirm`;
    if (lastAssistantMessage) {
      resumeAssistantStreaming(assistantMessageId);
    } else {
      appendAssistantPlaceholder(assistantMessageId);
    }
    let finalDisplayText = '';
    try {
      const accessToken = await getAccessToken();
      let finalResponse = null;
      await streamAdmin(
        {
          message: 'confirm',
          session_id: agentSessionId,
          selected_mode: 'qa',
          confirm: true,
          pending_action: agentPendingAction,
          access_token: accessToken,
        },
        (event) => {
          if (event.session_id) {
            setAgentSessionId(event.session_id);
          }
          if (event.type === 'status') {
            finalDisplayText = 'Executing the confirmed action...';
            updateAssistantPlaceholder(assistantMessageId, () => ({
              content: finalDisplayText,
            }));
          }
          if (event.type === 'activity') {
            const activityText = formatActivityLine(event.data) || 'Executing the confirmed action...';
            finalDisplayText = activityText;
            updateAssistantPlaceholder(assistantMessageId, (msg) => ({
              content: activityText,
              activity: [...(Array.isArray(msg.activity) ? msg.activity : []), event.data],
            }));
          }
          if (event.type === 'error') {
            finalDisplayText = `Confirmation failed: ${event.message || 'Unknown admin-service error'}`;
            updateAssistantPlaceholder(assistantMessageId, () => ({
              content: finalDisplayText,
            }));
          }
          const resolvedResponse = extractAdminStreamResponse(event);
          if (resolvedResponse) {
            finalResponse = resolvedResponse;
            finalDisplayText = resolvedResponse.answer || finalDisplayText || 'Action confirmed.';
            updateAssistantPlaceholder(assistantMessageId, (msg) => ({
              content: resolvedResponse.answer || msg.content || 'Action confirmed.',
              activity: mergeActivityItems(
                Array.isArray(msg.activity) ? msg.activity : [],
                Array.isArray(resolvedResponse.activity) ? resolvedResponse.activity : [],
              ),
            }));
          }
        }
      );
      setAgentPendingAction(finalResponse?.pending_action || null);
      finalDisplayText = finalResponse?.answer || finalDisplayText || 'Action confirmed.';
      updateAssistantPlaceholder(assistantMessageId, (msg) => ({
        content: finalResponse?.answer || msg.content || 'Action confirmed.',
      }));
    } catch (error) {
      finalDisplayText = `Confirmation failed: ${error.message}`;
      updateAssistantPlaceholder(assistantMessageId, () => ({
        content: finalDisplayText,
        activity: [],
      }));
    } finally {
      finishAssistantStreaming(assistantMessageId, finalDisplayText);
      setTyping(false);
    }
  };

  const rejectAgentAction = async () => {
    if (!agentPendingAction || typing) return;
    setTyping(true);
    const lastAssistantMessage = [...agentMsgs].reverse().find((msg) => msg.role === 'assistant');
    const assistantMessageId = lastAssistantMessage?.id || `${Date.now()}-reject`;
    if (lastAssistantMessage) {
      resumeAssistantStreaming(assistantMessageId);
    } else {
      appendAssistantPlaceholder(assistantMessageId);
    }
    let finalDisplayText = '';
    try {
      const accessToken = await getAccessToken();
      let finalResponse = null;
      await streamAdmin(
        {
          message: 'reject',
          session_id: agentSessionId,
          selected_mode: 'qa',
          reject: true,
          pending_action: agentPendingAction,
          access_token: accessToken,
        },
        (event) => {
          if (event.session_id) {
            setAgentSessionId(event.session_id);
          }
          if (event.type === 'status') {
            finalDisplayText = 'Rejecting the pending action...';
            updateAssistantPlaceholder(assistantMessageId, () => ({
              content: finalDisplayText,
            }));
          }
          if (event.type === 'activity') {
            const activityText = formatActivityLine(event.data) || 'Rejecting the pending action...';
            finalDisplayText = activityText;
            updateAssistantPlaceholder(assistantMessageId, (msg) => ({
              content: activityText,
              activity: [...(Array.isArray(msg.activity) ? msg.activity : []), event.data],
            }));
          }
          if (event.type === 'error') {
            finalDisplayText = `Rejection failed: ${event.message || 'Unknown admin-service error'}`;
            updateAssistantPlaceholder(assistantMessageId, () => ({
              content: finalDisplayText,
            }));
          }
          const resolvedResponse = extractAdminStreamResponse(event);
          if (resolvedResponse) {
            finalResponse = resolvedResponse;
            finalDisplayText = resolvedResponse.answer || finalDisplayText || 'Action canceled.';
            updateAssistantPlaceholder(assistantMessageId, (msg) => ({
              content: resolvedResponse.answer || msg.content || 'Action canceled.',
              activity: mergeActivityItems(
                Array.isArray(msg.activity) ? msg.activity : [],
                Array.isArray(resolvedResponse.activity) ? resolvedResponse.activity : [],
              ),
            }));
          }
        }
      );
      setAgentPendingAction(finalResponse?.pending_action || null);
      finalDisplayText = finalResponse?.answer || finalDisplayText || 'Action canceled.';
      updateAssistantPlaceholder(assistantMessageId, (msg) => ({
        content: finalResponse?.answer || msg.content || 'Action canceled.',
      }));
    } catch (error) {
      finalDisplayText = `Rejection failed: ${error.message}`;
      updateAssistantPlaceholder(assistantMessageId, () => ({
        content: finalDisplayText,
        activity: [],
      }));
    } finally {
      finishAssistantStreaming(assistantMessageId, finalDisplayText);
      setTyping(false);
    }
  };

  const handleTabChange = (nextTab) => {
    setTab(nextTab);
    if (nextTab === 'agent' && !agentWarningConfirmed) {
      setShowAgentWarningModal(true);
    }
  };

  const confirmAgentWarning = () => {
    setAgentWarningConfirmed(true);
    setShowAgentWarningModal(false);
  };

  const cancelAgentWarning = () => {
    setShowAgentWarningModal(false);
    setTab('documents');
  };

  const tabs = [
    { key: 'documents', label: 'Document Management', icon: FileText },
    { key: 'users', label: 'User Management', icon: User },
    { key: 'agent', label: 'Admin Agent Chat', icon: Bot },
  ];

  const getManagedUserStatus = (managedUser) => {
    if (managedUser.role === 'admin') return 'admin';
    if (managedUser.status) return managedUser.status;
    if (managedUser.blocked) return 'blocked';
    if (managedUser.invited) return 'invited';
    if (managedUser.validated) return 'validated';
    return 'pending';
  };

  const userStats = useMemo(() => ({
    total: managedUsers.length,
    admins: managedUsers.filter((managedUser) => managedUser.role === 'admin').length,
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
    if (userFilter === 'admin') return status === 'admin';
    if (userFilter === 'validated') return status === 'validated';
    if (userFilter === 'invited') return status === 'invited';
    if (userFilter === 'pending') return status === 'pending';
    if (userFilter === 'blocked') return status === 'blocked';
    return true;
  });

  const renderDocumentActions = (doc, mobile = false) => {
    const buttonClassName = mobile
      ? 'p-3.5 rounded-xl hover:bg-primary-500/10 transition-colors'
      : 'p-2.5 rounded-lg hover:bg-primary-500/10 transition-colors';
    const secondaryButtonClassName = mobile
      ? 'p-3.5 rounded-xl transition-colors'
      : 'p-2.5 rounded-lg transition-colors';
    const placeholderClassName = mobile ? 'p-3.5 invisible' : 'p-2.5 invisible';
    const iconSize = mobile ? 22 : 18;

    return (
    <>
      <button className={buttonClassName} style={{ color: theme === 'dark' ? '#ffffff' : 'var(--text-secondary)' }} title="View document" disabled={busyDocIds.has(doc.id)} onClick={() => viewDocument(doc)}><Eye size={iconSize} /></button>
      {doc.embedded || doc.status !== 'pending' || busyDocIds.has(doc.id) ? (
        <>
          <span className={placeholderClassName}><Check size={iconSize} /></span>
          <span className={placeholderClassName}><X size={iconSize} /></span>
        </>
      ) : (
        <>
          <button className={`${secondaryButtonClassName} hover:bg-success/10`} style={{ color: theme === 'dark' ? '#ffffff' : 'var(--text-secondary)' }} title="Validate and index if needed" disabled={busyDocIds.has(doc.id)} onClick={() => validateDocument(doc)}><Check size={iconSize} /></button>
          <button className={`${secondaryButtonClassName} hover:bg-warning/10`} style={{ color: theme === 'dark' ? '#ffffff' : 'var(--text-secondary)' }} title="Reject" disabled={busyDocIds.has(doc.id)} onClick={() => rejectDocument(doc)}><X size={iconSize} /></button>
        </>
      )}
      <button className={`${secondaryButtonClassName} hover:bg-danger/10`} style={{ color: '#ef4444' }} title="Remove" disabled={busyDocIds.has(doc.id)} onClick={() => removeDocument(doc)}><Trash2 size={iconSize} /></button>
    </>
    );
  };

  const renderUserActions = (managedUser, status, isCurrentUser, disableValidationAction, disableBlockAction, mobile = false) => {
    const buttonClassName = mobile
      ? 'p-3.5 rounded-xl transition-colors disabled:opacity-50'
      : 'p-2.5 rounded-lg transition-colors disabled:opacity-50';
    const placeholderClassName = mobile ? 'p-3.5 invisible' : 'p-2.5 invisible';
    const iconSize = mobile ? 22 : 18;

    return (
    <>
      {status !== 'validated' && status !== 'invited' && status !== 'admin' ? (
        <button
          onClick={() => (status === 'blocked' ? validateAgain(managedUser) : updateValidation(managedUser))}
          disabled={disableValidationAction}
          className={`${buttonClassName} hover:bg-success/10`}
          style={{ color: theme === 'dark' ? '#ffffff' : 'var(--text-secondary)' }}
          title={isCurrentUser ? 'You cannot change your own validation status' : status === 'blocked' ? 'Validate again' : 'Validate user'}
        >
          <Check size={iconSize} />
        </button>
      ) : (
        <span className={placeholderClassName}><Check size={iconSize} /></span>
      )}
      {status !== 'blocked' && status !== 'admin' ? (
        <button
          onClick={() => updateBlock(managedUser)}
          disabled={disableBlockAction}
          className={`${buttonClassName} hover:bg-warning/10`}
          style={{ color: theme === 'dark' ? '#ffffff' : 'var(--text-secondary)' }}
          title={isCurrentUser ? 'You cannot block your own account' : 'Block user'}
        >
          <Ban size={iconSize} />
        </button>
      ) : (
        <span className={placeholderClassName}><Ban size={iconSize} /></span>
      )}
      <button
        onClick={() => deleteUser(managedUser)}
        disabled={busyUserIds.has(managedUser.id) || managedUser.role === 'admin' || managedUser.id === user?.id}
        className={`${buttonClassName} hover:bg-danger/10`}
        style={{ color: '#ef4444' }}
        title="Delete user"
      >
        <Trash2 size={iconSize} />
      </button>
    </>
    );
  };

  return (
    <AnimatedPage className="h-full min-h-0 w-full overflow-y-auto overflow-x-hidden">
      <style>
        {`
          @media (max-width: 640px) {
            .admin-page-mobile-rounded button {
              border-radius: 9999px !important;
            }
          }
        `}
      </style>
      <div
        className="admin-page-mobile-rounded w-full min-h-full flex flex-col items-center relative overflow-x-hidden pb-8"
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

          <div
            className="w-full shrink-0 px-3 sm:px-5 md:px-8 lg:px-10 xl:px-12 flex justify-center"
            style={{ marginBottom: '24px', overflowX: 'hidden' }}
          >
            <div className="flex w-fit max-w-full flex-wrap justify-center gap-0">
          {tabs.map(({ key, label, icon: Icon }) => (
            <button key={key} onClick={() => handleTabChange(key)} className="flex items-center gap-2 px-6 text-sm font-medium transition-all" style={{ background: tab === key ? 'linear-gradient(135deg, #7c3aed, #06b6d4)' : 'var(--bg-secondary)', border: tab === key ? 'none' : '1px solid var(--border-color)', color: tab === key ? 'white' : 'var(--text-secondary)', boxShadow: tab === key ? '0 0 20px rgba(139,92,246,0.3)' : 'none', borderRadius: key === 'documents' ? '12px 0 0 50px' : key === 'agent' ? '0 12px 50px 0' : '0', padding: '16px 24px', minHeight: '56px', display: 'flex', alignItems: 'center' }}>
              <Icon size={16} /> {label}
            </button>
          ))}
          </div>
        </div>

        <div className="w-full flex justify-center" style={{ minHeight: 0 }}>
          <AnimatePresence mode="wait">
            {tab === 'documents' ? (
              <motion.div key="docs" className="min-h-full w-full flex justify-center relative" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                <div
                  className="min-h-full w-full mx-auto flex flex-col px-3 sm:px-5 md:px-8 lg:px-10 xl:px-12 mt-6 md:mt-12"
                  style={{ minHeight: 0, width: '85vw', maxWidth: '85vw', marginLeft: 'auto', marginRight: 'auto', overflowX: 'hidden' }}
                >

                  <div className="flex flex-col gap-3 shrink-0" style={{ marginTop: '24px', marginBottom: '16px' }}>
                    <div className="flex flex-col lg:flex-row items-stretch lg:items-center gap-3">
                      <div className="flex items-center gap-2 flex-1 w-full rounded-xl transition-all input-glow" style={{ border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', minHeight: '48px', paddingLeft: '24px', paddingRight: '24px' }}>
                        <Search size={16} style={{ color: 'var(--text-muted)' }} />
                        <input id="doc-search" type="text" placeholder="Search documents..." value={search} onChange={(e) => setSearch(e.target.value)} className="flex-1 bg-transparent outline-none text-sm min-w-0" style={{ color: 'var(--text-primary)' }} />
                      </div>
                      <div className="relative w-full lg:w-auto">
                        <select
                          id="status-filter"
                          value={filter}
                          onChange={(e) => setFilter(e.target.value)}
                          className="rounded-xl text-sm outline-none appearance-none"
                          style={{ border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', color: 'var(--text-primary)', minHeight: '48px', width: '100%', minWidth: '0', paddingLeft: '24px', paddingRight: '48px' }}
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
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                      <motion.button onClick={() => fileInputRef.current?.click()} className="flex items-center gap-2 px-6 rounded-xl text-sm font-medium text-white w-full justify-center" style={{ background: 'linear-gradient(135deg, #7c3aed, #06b6d4)', minHeight: '48px', minWidth: '0' }}>
                        <Upload size={16} /> Upload
                      </motion.button>
                      <motion.button
                        onClick={validateSelected}
                        disabled={selectedDocIds.size === 0}
                        className="flex items-center gap-2 px-6 rounded-xl text-sm font-medium text-white disabled:opacity-50 w-full justify-center"
                        style={{ background: 'linear-gradient(135deg, #16a34a, #15803d)', minHeight: '48px', minWidth: '0' }}
                      >
                        <Check size={16} /> Validate Selected
                      </motion.button>
                      <motion.button
                        onClick={rejectSelected}
                        disabled={selectedDocIds.size === 0}
                        className="flex items-center gap-2 px-6 rounded-xl text-sm font-medium text-white disabled:opacity-50 w-full justify-center"
                        style={{ background: 'linear-gradient(135deg, #dc2626, #b91c1c)', minHeight: '48px', minWidth: '0' }}
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
                    className="rounded-xl overflow-x-auto overflow-y-visible sm:max-h-[58vh] sm:overflow-y-auto"
                    style={{
                      border: '1px solid var(--border-color)',
                      marginTop: '16px',
                      minHeight: filtered.length === 0 ? '210px' : 'auto',
                    }}
                  >
                    <table className="w-full min-w-[880px] text-sm table-fixed">
                      <colgroup>
                        <col className="w-10" />
                        <col className="w-56" />
                        <col className="w-44" />
                        <col className="w-24" />
                        <col className="w-28" />
                        <col className="w-32" />
                        <col className="hidden w-0 sm:table-column sm:w-48" />
                      </colgroup>
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
                          <th className="px-5 sm:px-4 text-left text-base font-semibold" style={{ color: 'var(--text-secondary)', paddingTop: '12px', paddingBottom: '12px' }}>Document</th>
                          <th className="px-4 text-left text-base font-semibold" style={{ color: 'var(--text-secondary)', paddingTop: '12px', paddingBottom: '12px' }}>Uploader</th>
                          <th className="px-4 text-left text-base font-semibold" style={{ color: 'var(--text-secondary)', paddingTop: '12px', paddingBottom: '12px' }}>Size</th>
                          <th className="px-4 text-left text-base font-semibold" style={{ color: 'var(--text-secondary)', paddingTop: '12px', paddingBottom: '12px' }}>Date</th>
                          <th className="px-4 text-left text-base font-semibold" style={{ color: 'var(--text-secondary)', paddingTop: '12px', paddingBottom: '12px' }}>Status</th>
                          <th className="px-4 text-center text-base font-semibold w-48 hidden sm:table-cell" style={{ color: 'var(--text-secondary)', paddingTop: '12px', paddingBottom: '12px' }}>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filtered.map((doc) => (
                          <Fragment key={doc.id}>
                            <motion.tr className="transition-colors" style={{ borderBottom: '1px solid var(--border-color)', height: '76px' }}>
                              <td className="px-3 py-4 text-center align-middle">
                                <input
                                  type="checkbox"
                                  checked={selectedDocIds.has(doc.id)}
                                  onChange={() => toggleDocSelection(doc.id)}
                                  aria-label={`Select ${doc.name}`}
                                />
                              </td>
                              <td className="px-5 sm:px-4 py-4 align-middle">
                                <div className="flex items-center gap-3">
                                  <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0" style={{ background: 'rgba(139,92,246,0.08)' }}>
                                    <FileText size={14} style={{ color: 'var(--color-primary-400)' }} />
                                  </div>
                                  <div className="min-w-0 w-full">
                                    <div className="font-medium truncate" title={doc.name} style={{ color: 'var(--text-primary)' }}>{doc.name}</div>
                                    {doc.embedded && <div className="text-xs text-sky-400 truncate">Embedded</div>}
                                  </div>
                                </div>
                              </td>
                              <td className="px-4 py-4 align-middle" style={{ color: 'var(--text-secondary)' }}>
                                <div className="truncate" title={doc.uploaderLabel}>{doc.uploaderLabel}</div>
                              </td>
                              <td className="px-4 py-4 align-middle" style={{ color: 'var(--text-secondary)' }}>{doc.size}</td>
                              <td className="px-4 py-4 align-middle" style={{ color: 'var(--text-secondary)' }}>{doc.date}</td>
                              <td className="px-5 sm:px-4 py-4 align-middle"><StatusBadge status={doc.status} /></td>
                              <td className="px-4 py-4 w-48 align-middle hidden sm:table-cell">
                                <div className="grid grid-cols-4 justify-items-center items-center gap-2">
                                  {renderDocumentActions(doc)}
                                </div>
                              </td>
                            </motion.tr>
                            <tr className="sm:hidden" style={{ borderBottom: '1px solid var(--border-color)', height: '76px' }}>
                              <td colSpan={6} className="px-4 py-0">
                                <div className="grid h-[76px] grid-cols-4 justify-items-center items-center gap-3">
                                  {renderDocumentActions(doc, true)}
                                </div>
                              </td>
                            </tr>
                          </Fragment>
                        ))}
                        {filtered.length === 0 && (
                          <>
                            <tr>
                              <td colSpan={7} className="px-4 py-3">&nbsp;</td>
                            </tr>
                            <tr>
                              <td colSpan={7} className="px-4 py-10 text-center" style={{ color: 'var(--text-muted)' }}>
                                <div className="w-full text-center">
                                  <p className="text-lg font-semibold">
                                    {loadingDocs ? 'Loading documents...' : 'No documents found'}
                                  </p>
                                </div>
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
              <motion.div key="users" className="min-h-full w-full flex justify-center relative" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                <div
                  className="min-h-full w-full mx-auto flex flex-col px-3 sm:px-5 md:px-8 lg:px-10 xl:px-12 mt-6 md:mt-12"
                  style={{ minHeight: 0, width: '85vw', maxWidth: '85vw', marginLeft: 'auto', marginRight: 'auto', overflowX: 'hidden' }}
                >
                  <div className="flex flex-col gap-3 shrink-0" style={{ marginBottom: '16px' }}>
                    <div className="flex flex-col lg:flex-row items-stretch lg:items-center gap-3">
                    <div className="flex-1 w-full flex items-center gap-2 rounded-xl transition-all input-glow" style={{ border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', minHeight: '48px', paddingLeft: '24px', paddingRight: '24px' }}>
                      <Search size={16} style={{ color: 'var(--text-muted)' }} />
                      <input
                        type="text"
                        placeholder="Search users by email..."
                        value={userSearch}
                        onChange={(event) => setUserSearch(event.target.value)}
                        className="flex-1 bg-transparent outline-none text-sm min-w-0"
                        style={{ color: 'var(--text-primary)' }}
                      />
                    </div>
                    <div className="relative w-full lg:w-auto">
                      <select
                        id="user-status-filter"
                        value={userFilter}
                        onChange={(event) => setUserFilter(event.target.value)}
                        className="rounded-xl text-sm outline-none appearance-none"
                        style={{ border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', color: 'var(--text-primary)', minHeight: '48px', minWidth: '0', width: '100%', paddingLeft: '24px', paddingRight: '48px' }}
                        >
                          <option value="all">All Users</option>
                          <option value="admin">Admin</option>
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
                    </div>
                    <div className="flex flex-col sm:flex-row items-stretch gap-2 w-full">
                      <input
                        type="email"
                        placeholder="Invite user email"
                        value={inviteEmail}
                        onChange={(event) => setInviteEmail(event.target.value)}
                        className="rounded-xl text-sm outline-none"
                        style={{ border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', color: 'var(--text-primary)', minHeight: '48px', minWidth: '0', width: '100%', paddingLeft: '20px', paddingRight: '20px' }}
                      />
                      <motion.button
                        onClick={handleInvite}
                        disabled={inviting || !inviteEmail.trim()}
                        className="flex items-center gap-2 px-6 rounded-xl text-sm font-medium text-white disabled:opacity-50 w-full sm:w-auto justify-center"
                        style={{ background: 'linear-gradient(135deg, #7c3aed, #06b6d4)', minHeight: '48px', minWidth: '0' }}
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

                  <div className="grid grid-cols-2 md:grid-cols-6 gap-3 shrink-0" style={{ marginBottom: '16px' }}>
                    {[
                      { l: 'Total', v: userStats.total, color: 'var(--color-primary-400)' },
                      { l: 'Admins', v: userStats.admins, color: '#8b5cf6' },
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

                  <div className="rounded-xl overflow-x-auto overflow-y-visible sm:max-h-[58vh] sm:overflow-y-auto" style={{ border: '1px solid var(--border-color)', marginTop: '16px', minHeight: filteredUsers.length === 0 ? '210px' : 'auto' }}>
                    <table className="w-full min-w-[560px] text-sm table-fixed">
                      <colgroup>
                        <col />
                        <col className="w-36" />
                        <col className="hidden w-0 sm:table-column sm:w-40" />
                      </colgroup>
                      <thead>
                        <tr className="sticky top-0 z-10" style={{ background: 'var(--bg-tertiary)', borderBottom: '1px solid var(--border-color)', minHeight: '62px' }}>
                          <th className="text-left text-base font-semibold" style={{ color: 'var(--text-secondary)', paddingTop: '12px', paddingBottom: '12px', paddingLeft: '28px', paddingRight: '16px' }}>User Info</th>
                          <th className="px-5 sm:px-4 text-left text-base font-semibold w-32 sm:w-auto" style={{ color: 'var(--text-secondary)', paddingTop: '12px', paddingBottom: '12px' }}>Status</th>
                          <th className="px-4 text-center text-base font-semibold w-40 hidden sm:table-cell" style={{ color: 'var(--text-secondary)', paddingTop: '12px', paddingBottom: '12px' }}>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredUsers.map((managedUser) => {
                          const status = getManagedUserStatus(managedUser);
                          const isCurrentUser = managedUser.id === user?.id;
                          const disableValidationAction = busyUserIds.has(managedUser.id) || managedUser.role === 'admin' || isCurrentUser;
                          const disableBlockAction = busyUserIds.has(managedUser.id) || managedUser.role === 'admin' || isCurrentUser;
                          const statusCfg = status === 'admin'
                            ? { bg: 'rgba(124,58,237,0.12)', color: '#8b5cf6', border: '1px solid rgba(124,58,237,0.25)', label: 'Admin' }
                            : status === 'validated'
                            ? { bg: 'rgba(16,185,129,0.1)', color: '#10b981', border: '1px solid rgba(16,185,129,0.2)', label: 'Validated' }
                            : status === 'invited'
                              ? { bg: 'rgba(56,189,248,0.12)', color: '#38bdf8', border: '1px solid rgba(56,189,248,0.25)', label: 'Invited' }
                            : status === 'blocked'
                              ? { bg: 'rgba(239,68,68,0.1)', color: '#ef4444', border: '1px solid rgba(239,68,68,0.2)', label: 'Blocked' }
                              : { bg: 'rgba(245,158,11,0.1)', color: '#f59e0b', border: '1px solid rgba(245,158,11,0.2)', label: 'Pending' };
                          return (
                          <Fragment key={managedUser.id}>
                            <tr className="transition-colors" style={{ borderBottom: '1px solid var(--border-color)', height: '76px' }}>
                              <td className="py-4 align-middle" style={{ paddingLeft: '28px', paddingRight: '16px' }}>
                                <div className="flex items-center gap-3 min-w-0" style={{ paddingLeft: '4px' }}>
                                  <div className="w-9 h-9 rounded-full overflow-hidden flex items-center justify-center shrink-0" style={{ background: 'rgba(139,92,246,0.1)', border: '1px solid var(--border-color)' }}>
                                    {managedUser.profile_picture ? (
                                      <img src={managedUser.profile_picture} alt="Profile" className="w-full h-full object-cover" />
                                    ) : (
                                      <User size={14} style={{ color: 'var(--text-muted)' }} />
                                    )}
                                  </div>
                                  <div className="min-w-0 w-full">
                                    <div className="font-medium truncate" title={managedUser.username || 'No username'} style={{ color: 'var(--text-primary)' }}>
                                      {managedUser.username || 'No username'}
                                    </div>
                                    <div className="text-xs truncate" title={managedUser.email} style={{ color: 'var(--text-muted)' }}>
                                      {managedUser.email}
                                    </div>
                                    <div className="text-xs truncate" title={managedUser.phone_number || 'No phone'} style={{ color: 'var(--text-muted)' }}>
                                      {managedUser.phone_number || 'No phone'}
                                    </div>
                                  </div>
                                </div>
                              </td>
                              <td className="px-5 sm:px-4 py-4 align-middle w-32 sm:w-auto">
                                <span className="inline-flex items-center py-1 rounded-full text-xs font-medium" style={{ background: statusCfg.bg, color: statusCfg.color, border: statusCfg.border, paddingLeft: '14px', paddingRight: '14px' }}>
                                  {statusCfg.label}
                                </span>
                              </td>
                              <td className="px-4 py-4 align-middle w-40 hidden sm:table-cell">
                                <div className="grid grid-cols-3 justify-items-center items-center gap-2">
                                  {renderUserActions(managedUser, status, isCurrentUser, disableValidationAction, disableBlockAction)}
                                </div>
                              </td>
                            </tr>
                            <tr className="sm:hidden" style={{ borderBottom: '1px solid var(--border-color)', height: '76px' }}>
                              <td colSpan={2} className="px-4 py-0">
                                <div className="grid h-[76px] grid-cols-3 justify-items-center items-center gap-3">
                                  {renderUserActions(managedUser, status, isCurrentUser, disableValidationAction, disableBlockAction, true)}
                                </div>
                              </td>
                            </tr>
                          </Fragment>
                        )})}
                        {filteredUsers.length === 0 && (
                          <>
                            <tr>
                              <td colSpan={3} className="px-4 py-3">&nbsp;</td>
                            </tr>
                            <tr>
                              <td colSpan={3} className="px-4 py-10 text-center" style={{ color: 'var(--text-muted)' }}>
                                <div className="w-full text-center">
                                  <p className="text-lg font-semibold">
                                    {loadingManagedUsers ? 'Loading users...' : 'No users found'}
                                  </p>
                                </div>
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
              <motion.div key="agent" className="min-h-full w-full flex justify-center" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                <div
                  className="w-full mx-auto flex flex-col px-3 sm:px-5 md:px-8 lg:px-10 xl:px-12 mt-8 md:mt-16"
                  style={{ minHeight: 'calc(100vh - 220px)', width: '85vw', maxWidth: '85vw', marginLeft: 'auto', marginRight: 'auto', overflowX: 'hidden' }}
                >
                  <div className="flex-1 w-full" style={{ overflowY: 'auto', overflowX: 'hidden', scrollBehavior: 'smooth', minHeight: 0, scrollbarGutter: 'stable', paddingTop: '32px', paddingBottom: '32px' }}>
                    <div className="mx-auto w-full">
                      {agentMsgs.map((msg) => (
                        <motion.div key={msg.id} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : ''}`} style={{ marginBottom: '32px' }} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
                          {msg.role === 'assistant' && <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mt-1" style={{ background: 'linear-gradient(135deg, #f59e0b, #ef4444)', boxShadow: '0 0 12px rgba(245,158,11,0.3)' }}><Bot size={15} className="text-white" /></div>}
                          <div
                            className={`max-w-[80%] rounded-2xl ${msg.role === 'user' ? 'rounded-br-md' : 'rounded-bl-md'}`}
                            style={msg.role === 'user'
                              ? { background: 'linear-gradient(135deg, #7c3aed, #5b21b6)', color: 'white', boxShadow: '0 4px 15px rgba(139,92,246,0.2)', padding: '16px 24px' }
                              : msg.isStreaming
                                ? { background: 'var(--bg-tertiary)', color: 'var(--text-muted)', padding: '16px 24px' }
                                : { background: 'var(--bg-tertiary)', color: 'var(--text-primary)', border: '1px solid var(--border-color)', padding: '16px 24px' }}
                          >
                            {msg.role === 'assistant' && ((Array.isArray(msg.activity) && msg.activity.length > 0) || (Array.isArray(msg.sources) && msg.sources.length > 0)) && (
                              <div className="mb-3">
                                <button
                                  type="button"
                                  onClick={() => toggleAssistantDetails(msg.id)}
                                  className="inline-flex items-center gap-2 text-xs font-medium"
                                  style={{ color: 'var(--text-muted)' }}
                                >
                                  <ChevronDown
                                    size={14}
                                    style={{
                                      transform: msg.detailsOpen ? 'rotate(180deg)' : 'rotate(0deg)',
                                      transition: 'transform 160ms ease',
                                    }}
                                  />
                                  {msg.detailsOpen ? 'Hide details' : 'Show details'}
                                </button>
                                {msg.detailsOpen && (
                                  <div
                                    className="mt-3 rounded-xl p-3"
                                    style={{
                                      background: 'rgba(15,23,42,0.04)',
                                    }}
                                  >
                                    {Array.isArray(msg.activity) && msg.activity.length > 0 && (
                                      <div className="space-y-3">
                                        {msg.activity.map((activity, index) => (
                                          <div
                                            key={`${msg.id}-activity-${index}`}
                                            className="rounded-xl px-4 text-xs"
                                            style={{
                                              background: activity.status === 'failed'
                                                ? 'rgba(239,68,68,0.08)'
                                                : activity.status === 'completed'
                                                  ? 'rgba(16,185,129,0.08)'
                                                  : 'rgba(245,158,11,0.08)',
                                              border: activity.status === 'failed'
                                                ? '1px solid rgba(239,68,68,0.18)'
                                                : activity.status === 'completed'
                                                  ? '1px solid rgba(16,185,129,0.18)'
                                                  : '1px solid rgba(245,158,11,0.18)',
                                              color: 'var(--text-secondary)',
                                              marginTop: '4px',
                                              marginBottom: '4px',
                                              paddingTop: '16px',
                                              paddingBottom: '16px',
                                            }}
                                          >
                                            <div
                                              style={{
                                                display: 'grid',
                                                gridTemplateColumns: 'minmax(0, 1fr) 88px',
                                                alignItems: 'center',
                                                columnGap: '12px',
                                              }}
                                            >
                                              <span style={{ minWidth: 0, paddingLeft: '8px' }}>{formatActivityLine(activity)}</span>
                                              <span
                                                className="uppercase tracking-wide"
                                                style={{ fontSize: '10px', whiteSpace: 'nowrap', opacity: 0.9, textAlign: 'left' }}
                                              >
                                                {activity.status}
                                              </span>
                                            </div>
                                          </div>
                                        ))}
                                      </div>
                                    )}
                                    {Array.isArray(msg.sources) && msg.sources.length > 0 && (
                                      <div className={Array.isArray(msg.activity) && msg.activity.length > 0 ? 'mt-3' : ''}>
                                        <p className="text-xs font-medium mb-2" style={{ color: 'var(--text-muted)' }}>Citations</p>
                                        <div className="flex flex-wrap gap-1.5">
                                          {msg.sources.map((src, i) => (
                                            <span key={i} className="text-xs px-2.5 py-0.5 rounded-full" style={{ background: 'rgba(139,92,246,0.08)', color: 'var(--color-primary-400)', border: '1px solid rgba(139,92,246,0.15)' }}>
                                              {src}
                                            </span>
                                          ))}
                                        </div>
                                      </div>
                                    )}
                                  </div>
                                )}
                              </div>
                            )}
                            <div
                              className="text-sm leading-relaxed mb-2"
                              style={{
                                marginTop: msg.role === 'assistant' && msg.detailsOpen ? '20px' : '8px',
                                color: msg.role === 'assistant' && msg.isStreaming ? 'var(--text-muted)' : undefined,
                              }}
                            >
                              {msg.role === 'assistant' ? (
                                msg.isStreaming ? (
                                  <p style={{ margin: '8px 0 12px', whiteSpace: 'pre-line' }}>
                                    <AnimatedAssistantText text={msg.content} animate={Boolean(msg.isStreaming)} />
                                  </p>
                                ) : (
                                  <MarkdownLite text={msg.content} />
                                )
                              ) : (
                                <p style={{ margin: '8px 0 12px', whiteSpace: 'pre-line' }}>{msg.content}</p>
                              )}
                            </div>
                            <p className={`text-xs mt-2 ${msg.role === 'user' ? 'text-white/50' : ''}`} style={msg.role === 'assistant' ? { color: 'var(--text-muted)' } : {}}>{msg.timestamp}</p>
                          </div>
                          {msg.role === 'user' && <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mt-1" style={{ background: 'linear-gradient(135deg, #52525b, #27272a)' }}><User size={15} className="text-white" /></div>}
                        </motion.div>
                      ))}
                      <div ref={endRef} />
                    </div>
                  </div>
                  <div className="w-full mt-auto pt-3 pb-6">
                    <div className="mx-auto w-full">
                      <div className="w-full">
                        {agentPendingAction && (
                          <div
                            className="mb-3 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 rounded-2xl"
                            style={{
                              background: 'rgba(245,158,11,0.08)',
                              border: '1px solid rgba(245,158,11,0.22)',
                              padding: '14px 18px',
                            }}
                          >
                            <div className="min-w-0">
                              <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                                Confirmation required
                              </p>
                              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                                {agentPendingAction.summary || 'This action needs your confirmation before execution.'}
                              </p>
                            </div>
                            <div className="flex items-center gap-2 shrink-0">
                              <motion.button
                                onClick={rejectAgentAction}
                                disabled={typing}
                                aria-label="Reject pending action"
                                title="Reject pending action"
                                className="rounded-xl disabled:opacity-50 flex items-center justify-center"
                                style={{
                                  minHeight: '42px',
                                  minWidth: '42px',
                                  border: '1px solid rgba(239,68,68,0.28)',
                                  background: 'rgba(239,68,68,0.08)',
                                  color: '#ef4444',
                                }}
                              >
                                <X size={16} />
                              </motion.button>
                              <motion.button
                                onClick={confirmAgentAction}
                                disabled={typing}
                                className="rounded-xl text-sm font-medium text-white disabled:opacity-50 shrink-0"
                                style={{
                                  background: 'linear-gradient(135deg, #f59e0b, #ef4444)',
                                  minHeight: '42px',
                                  paddingLeft: '18px',
                                  paddingRight: '18px',
                                }}
                              >
                                Confirm
                              </motion.button>
                            </div>
                          </div>
                        )}
                        <div className="flex flex-col sm:flex-row items-stretch sm:items-end gap-3 rounded-2xl p-4 sm:p-6 transition-all input-glow" style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)' }}>
                          <textarea id="admin-agent-input" value={agentInput} onChange={(e) => setAgentInput(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendAgent(); } }} placeholder='Try: "refresh status", "embed validated", or "run evaluation"' rows={3} disabled={!agentWarningConfirmed} className="flex-1 bg-transparent outline-none text-sm resize-none max-h-56 disabled:opacity-50" style={{ color: 'var(--text-primary)', padding: '16px 18px' }} />
                          <motion.button id="admin-send" onClick={sendAgent} disabled={!agentWarningConfirmed || !agentInput.trim() || typing} className="rounded-xl disabled:opacity-20 shrink-0 w-full sm:w-auto" style={{ padding: '16px 22px', marginRight: '0px' }}>
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

        {showAgentWarningModal && tab === 'agent' && (
          <>
            <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-md" />
            <div className="fixed inset-0 z-50 flex items-center justify-center p-10 md:p-16">
              <motion.div
                initial={{ opacity: 0, scale: 0.97, y: 8 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                className="flex w-full max-w-2xl flex-col items-center justify-center gap-10 rounded-3xl p-12 text-center md:p-16"
                style={{
                  background: 'var(--bg-secondary)',
                  border: '1px solid rgba(245,158,11,0.22)',
                  boxShadow: '0 24px 80px rgba(2,6,23,0.35)',
                  minHeight: '420px',
                }}
              >
                <div className="flex flex-col items-center justify-center gap-8">
                  <div
                    className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl"
                    style={{ background: 'rgba(245,158,11,0.14)', color: '#f59e0b' }}
                  >
                    <AlertTriangle size={24} />
                  </div>
                  <div className="min-w-0 max-w-3xl">
                    <h2 className="text-xl font-semibold" style={{ color: 'var(--text-primary)' }}>
                      Confirm before opening admin chat
                    </h2>
                    <p className="mt-6 text-base leading-7" style={{ color: 'var(--text-secondary)' }}>
                      {ADMIN_AGENT_WARNING}
                    </p>
                    <p className="mt-6 text-base leading-7" style={{ color: 'var(--text-secondary)' }}>
                      Continue only if you understand that this assistant can guide changes, but the final decision and its consequences remain yours.
                    </p>
                  </div>
                </div>
                <div className="flex justify-center gap-4">
                  <button
                    type="button"
                    onClick={cancelAgentWarning}
                    onMouseEnter={() => setHoveredWarningButton('cancel')}
                    onMouseLeave={() => setHoveredWarningButton(null)}
                    className="rounded-xl px-8 py-4 text-sm font-medium"
                    style={{
                      border: hoveredWarningButton === 'cancel'
                        ? '1px solid rgba(239,68,68,0.3)'
                        : '1px solid var(--border-color)',
                      color: hoveredWarningButton === 'cancel' ? '#ffffff' : 'var(--text-secondary)',
                      background: hoveredWarningButton === 'cancel'
                        ? 'linear-gradient(135deg, #ef4444, #dc2626)'
                        : 'transparent',
                      minWidth: '148px',
                      minHeight: '56px',
                      transition: 'all 160ms ease',
                    }}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={confirmAgentWarning}
                    onMouseEnter={() => setHoveredWarningButton('confirm')}
                    onMouseLeave={() => setHoveredWarningButton(null)}
                    className="rounded-xl px-10 py-4 text-sm font-medium text-white"
                    style={{
                      background: hoveredWarningButton === 'confirm'
                        ? 'linear-gradient(135deg, #06b6d4, #2563eb)'
                        : 'linear-gradient(135deg, #f59e0b, #ef4444)',
                      boxShadow: hoveredWarningButton === 'confirm'
                        ? '0 14px 34px rgba(37,99,235,0.24)'
                        : '0 12px 30px rgba(239,68,68,0.18)',
                      minWidth: '168px',
                      minHeight: '56px',
                      transition: 'all 160ms ease',
                    }}
                  >
                    Confirm
                  </button>
                </div>
              </motion.div>
            </div>
          </>
        )}
      </div>
    </AnimatedPage>
  );
}
