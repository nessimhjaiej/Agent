import { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import {
  ShieldAlert,
  ShieldCheck,
  AlertTriangle,
  Activity,
  Clock,
  CheckCircle2,
  TrendingUp,
  Filter,
} from 'lucide-react';
import AnimatedPage from '../components/AnimatedPage';
import {
  getSecurityAlertsSummary,
  getSecurityLoginAttemptsSummary,
  listSecurityAlerts,
  resolveSecurityAlert,
} from '../config/api';

function formatDateTime(value) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '-';
  return new Intl.DateTimeFormat([], {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

function formatLabel(value) {
  return String(value || '')
    .split('_')
    .filter(Boolean)
    .map((part) => part[0]?.toUpperCase() + part.slice(1).toLowerCase())
    .join(' ');
}

function extractAlertMetadataEntries(alert) {
  const metadata = alert?.metadata && typeof alert.metadata === 'object' ? alert.metadata : {};
  const preferredOrder = [
    'email',
    'role',
    'user_id',
    'tool',
    'service_name',
    'document_id',
    'dataset_path',
    'change_summary',
    'change_keys',
    'client_ip',
    'path',
    'method',
    'failed_attempts',
    'window_minutes',
    'query_preview',
    'reason',
  ];

  const orderedKeys = [
    ...preferredOrder.filter((key) => metadata[key]),
    ...Object.keys(metadata).filter((key) => !preferredOrder.includes(key) && metadata[key]),
  ];

  return orderedKeys.map((key) => ({
    key,
    label: formatLabel(key),
    value: typeof metadata[key] === 'object' ? JSON.stringify(metadata[key]) : String(metadata[key]),
  }));
}

const sevCfg = {
  critical: { bg: 'rgba(239,68,68,0.08)', glow: 'rgba(239,68,68,0.15)', text: '#ef4444', border: 'rgba(239,68,68,0.15)', icon: ShieldAlert },
  warning: { bg: 'rgba(245,158,11,0.08)', glow: 'rgba(245,158,11,0.15)', text: '#f59e0b', border: 'rgba(245,158,11,0.15)', icon: AlertTriangle },
  info: { bg: 'rgba(59,130,246,0.08)', glow: 'rgba(59,130,246,0.15)', text: '#3b82f6', border: 'rgba(59,130,246,0.15)', icon: Activity },
};

const statusStyles = {
  active: { bg: 'rgba(239,68,68,0.1)', color: '#ef4444', border: 'rgba(239,68,68,0.2)' },
  resolved: { bg: 'rgba(16,185,129,0.1)', color: '#10b981', border: 'rgba(16,185,129,0.2)' },
};
const SECURITY_REFRESH_INTERVAL_MS = 3000;

export default function SecurityPage() {
  const [includeResolved, setIncludeResolved] = useState(false);
  const [eventTypeFilter, setEventTypeFilter] = useState('all');
  const [severityFilter, setSeverityFilter] = useState('all');
  const [summary, setSummary] = useState({
    active_alerts: 0,
    critical_alerts: 0,
    warning_alerts: 0,
    info_alerts: 0,
  });
  const [alerts, setAlerts] = useState([]);
  const [loginAttemptsSummary, setLoginAttemptsSummary] = useState({
    enabled: false,
    window_hours: 24,
    total_attempts: 0,
    failed_attempts: 0,
    successful_attempts: 0,
    unique_emails: 0,
    recent_failed_attempts: [],
    top_targeted_accounts: [],
  });
  const [loading, setLoading] = useState(true);
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);
  const [error, setError] = useState('');
  const [busyAlertIds, setBusyAlertIds] = useState(new Set());

  const loadSecurityData = async (resolved = includeResolved) => {
    setLoading(true);
    setError('');
    try {
      const [nextSummary, alertsResponse, nextLoginAttemptsSummary] = await Promise.all([
        getSecurityAlertsSummary(),
        listSecurityAlerts(resolved),
        getSecurityLoginAttemptsSummary(),
      ]);
      setSummary(nextSummary);
      setAlerts(alertsResponse.alerts || []);
      setLoginAttemptsSummary(nextLoginAttemptsSummary);
    } catch (nextError) {
      setError(nextError.message || 'Failed to load security alerts');
    } finally {
      setHasLoadedOnce(true);
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSecurityData(includeResolved);
    const intervalId = window.setInterval(() => loadSecurityData(includeResolved), SECURITY_REFRESH_INTERVAL_MS);

    const refreshOnVisibility = () => {
      if (document.visibilityState === 'visible') {
        loadSecurityData(includeResolved);
      }
    };

    const refreshOnFocus = () => {
      loadSecurityData(includeResolved);
    };

    document.addEventListener('visibilitychange', refreshOnVisibility);
    window.addEventListener('focus', refreshOnFocus);

    return () => {
      window.clearInterval(intervalId);
      document.removeEventListener('visibilitychange', refreshOnVisibility);
      window.removeEventListener('focus', refreshOnFocus);
    };
  }, [includeResolved]);

  const eventTypeOptions = useMemo(() => {
    const unique = [...new Set(alerts.map((alert) => alert.event_type).filter(Boolean))];
    return unique.sort();
  }, [alerts]);

  const filteredAlerts = useMemo(
    () =>
      alerts.filter((alert) => {
        if (!includeResolved && alert.status !== 'active') return false;
        if (eventTypeFilter !== 'all' && alert.event_type !== eventTypeFilter) return false;
        if (severityFilter !== 'all' && alert.severity !== severityFilter) return false;
        return true;
      }),
    [alerts, eventTypeFilter, includeResolved, severityFilter]
  );
  const isInitialLoading = loading && !hasLoadedOnce;
  const securityEventsMaxHeightClass = filteredAlerts.length <= 1 ? 'max-h-[460px] sm:max-h-[320px]' : 'max-h-[1400px] sm:max-h-[984px]';

  const markBusy = (alertId, value) => {
    setBusyAlertIds((prev) => {
      const next = new Set(prev);
      if (value) next.add(alertId);
      else next.delete(alertId);
      return next;
    });
  };

  const handleResolve = async (alertId) => {
    markBusy(alertId, true);
    setError('');
    try {
      await resolveSecurityAlert(alertId);
      await loadSecurityData(includeResolved);
    } catch (nextError) {
      setError(nextError.message || 'Failed to resolve alert');
    } finally {
      markBusy(alertId, false);
    }
  };

  return (
    <AnimatedPage className="mt-6 h-full min-h-0 w-full overflow-y-auto overflow-x-hidden md:mt-8">
      <div className="w-full min-h-full overflow-x-hidden px-4 pt-8 pb-3 sm:px-4 sm:pt-10 sm:pb-4 md:px-6 md:pt-12 md:pb-5 lg:px-8 lg:pt-14 lg:pb-6">
        <div className="mx-auto w-full max-w-[1560px] space-y-6 md:space-y-8">
          <div className="pt-6 md:pt-8">
            <div className="grid grid-cols-1 gap-3 px-2 sm:grid-cols-2 xl:grid-cols-4 md:gap-4 md:px-2">
            {[
              { label: 'Active Alerts', value: summary.active_alerts, sub: 'Not resolved yet', icon: ShieldAlert, color: '#ef4444', glow: 'rgba(239,68,68,0.15)' },
              { label: 'Critical Alerts', value: summary.critical_alerts, sub: 'Highest priority', icon: AlertTriangle, color: '#f59e0b', glow: 'rgba(245,158,11,0.15)' },
              { label: 'Warning Alerts', value: summary.warning_alerts, sub: 'Watch closely', icon: TrendingUp, color: 'var(--color-primary-400)', glow: 'rgba(139,92,246,0.15)' },
              { label: 'Info Alerts', value: summary.info_alerts, sub: 'Confirmed changes and telemetry', icon: ShieldCheck, color: '#10b981', glow: 'rgba(16,185,129,0.15)' },
            ].map((card, i) => (
              <motion.div
                key={card.label}
                className="min-w-0 rounded-xl px-7 py-6 md:px-8 md:py-7"
                style={{
                  background: 'var(--bg-secondary)',
                  border: '1px solid var(--border-color)',
                }}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.08 }}
                whileHover={{
                  boxShadow: `0 0 25px ${card.glow}`,
                  borderColor: card.glow,
                }}
              >
                <div className="flex min-h-[152px] flex-col justify-center py-1">
                  <div className="mb-5 mt-1 flex justify-center">
                    <div
                      className="flex h-10 w-10 items-center justify-center rounded-xl"
                      style={{ background: card.glow }}
                    >
                      <card.icon size={20} style={{ color: card.color }} />
                    </div>
                  </div>
                  <p className="mb-1 text-center text-2xl font-bold font-display break-words md:text-3xl" style={{ color: card.color }}>{card.value}</p>
                  <p className="mt-3 mb-1 text-center text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{card.label}</p>
                </div>

              </motion.div>
            ))}
            </div>
          </div>

          <div className="pt-4">
            <div className="h-2 md:h-3" />
            <div className="flex flex-col gap-4 px-3 lg:flex-row lg:items-center lg:justify-between">
              <div className="min-w-0">
                <h2 className="text-lg font-semibold font-display" style={{ color: 'var(--text-primary)' }}>
                  Login Attempts
                </h2>
              </div>
              {!loginAttemptsSummary.enabled && (
                <span
                  className="inline-flex min-h-[40px] items-center justify-center rounded-full px-4 py-2.5 text-sm font-medium"
                  style={{
                    background: 'rgba(245,158,11,0.1)',
                    color: '#f59e0b',
                  }}
                >
                  Supabase read disabled
                </span>
              )}
            </div>
            <div className="h-3 md:h-4" />

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4 md:gap-4">
              {[
                { label: 'Total Attempts', value: loginAttemptsSummary.total_attempts, color: '#3b82f6', glow: 'rgba(59,130,246,0.15)', icon: Activity },
                { label: 'Failed Attempts', value: loginAttemptsSummary.failed_attempts, color: '#ef4444', glow: 'rgba(239,68,68,0.15)', icon: ShieldAlert },
                { label: 'Successful Attempts', value: loginAttemptsSummary.successful_attempts, color: '#10b981', glow: 'rgba(16,185,129,0.15)', icon: ShieldCheck },
                { label: 'Unique Emails', value: loginAttemptsSummary.unique_emails, color: '#f59e0b', glow: 'rgba(245,158,11,0.15)', icon: TrendingUp },
              ].map((card, i) => (
                <motion.div
                  key={card.label}
                  className="min-w-0 rounded-xl p-5 md:p-6"
                  style={{
                    background: 'var(--bg-secondary)',
                    border: '1px solid var(--border-color)',
                  }}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.08 }}
                  whileHover={{
                    boxShadow: `0 0 25px ${card.glow}`,
                    borderColor: card.glow,
                  }}
                >
                  <div className="flex min-h-[126px] flex-col items-center justify-center text-center">
                  <div className="mb-4 flex justify-center">
                    <div
                      className="flex h-10 w-10 items-center justify-center rounded-xl"
                      style={{ background: card.glow }}
                    >
                      <card.icon size={20} style={{ color: card.color }} />
                    </div>
                  </div>
                  <div className="text-center">
                    <p className="text-2xl font-bold font-display break-words md:text-3xl" style={{ color: card.color }}>{card.value}</p>
                    <p className="mt-2 text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{card.label}</p>
                  </div>
                  </div>
                </motion.div>
              ))}
            </div>

            <div className="mt-10 grid grid-cols-1 gap-5 xl:grid-cols-2 md:mt-12 md:gap-6">
              <div
                className="overflow-hidden rounded-xl"
                style={{}}
              >
                <div className="px-6">
                  <div className="h-6 md:h-8" />
                  <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                    Recent Failed Attempts
                  </h3>
                  <div className="h-5 md:h-6" />
                </div>
                <div className="max-h-[352px] overflow-auto pt-4">
                  {loginAttemptsSummary.recent_failed_attempts.length > 0 ? loginAttemptsSummary.recent_failed_attempts.map((attempt, index) => (
                    <div
                      key={`${attempt.email}-${attempt.timestamp}-${index}`}
                      className="grid min-h-[88px] grid-cols-[minmax(0,1fr)_140px] items-center gap-3 px-6 py-0"
                      style={{ borderBottom: '1px solid var(--border-color)' }}
                    >
                      <p className="min-w-0 truncate text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                        {attempt.email || 'unknown'}
                      </p>
                      <div className="justify-self-start">
                        <p className="text-xs text-left" style={{ color: 'var(--text-muted)' }}>
                          {formatDateTime(attempt.timestamp)}
                        </p>
                      </div>
                    </div>
                  )) : (
                    <div className="px-6 py-10 text-center text-sm" style={{ color: 'var(--text-muted)' }}>
                      No failed attempts in the selected window.
                    </div>
                  )}
                </div>
              </div>

              <div
                className="overflow-hidden rounded-xl"
                style={{}}
              >
                <div className="px-6">
                  <div className="h-6 md:h-8" />
                  <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                    Top Targeted Accounts
                  </h3>
                  <div className="h-5 md:h-6" />
                </div>
                <div className="max-h-[352px] overflow-auto pt-4">
                  {loginAttemptsSummary.top_targeted_accounts.length > 0 ? loginAttemptsSummary.top_targeted_accounts.map((item) => (
                    <div
                      key={item.email}
                      className="grid min-h-[88px] grid-cols-[minmax(0,1fr)_148px] items-center gap-3 px-6 py-0"
                      style={{ borderBottom: '1px solid var(--border-color)' }}
                    >
                      <p className="min-w-0 truncate text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                        {item.email}
                      </p>
                      <div className="justify-self-start">
                        <span
                          className="inline-flex min-h-[40px] min-w-[112px] items-center justify-center rounded-full px-4 py-2.5 text-sm font-medium"
                          style={{
                            background: 'rgba(239,68,68,0.1)',
                            color: '#ef4444',
                            border: '1px solid rgba(239,68,68,0.2)',
                          }}
                        >
                          {item.failed_attempts} failed
                        </span>
                      </div>
                    </div>
                  )) : (
                    <div className="px-6 py-10 text-center text-sm" style={{ color: 'var(--text-muted)' }}>
                      No targeted accounts detected.
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>

          <div
            className="min-w-0 rounded-xl px-6 py-5 sm:px-8 md:px-10 md:py-6"
            style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)' }}
          >
            <div className="h-2 md:h-3" />
            <div className="flex flex-col gap-5 px-1 xl:flex-row xl:items-start xl:justify-between">
              <div className="min-w-0 xl:translate-x-4">
                <h2 className="text-lg font-semibold font-display" style={{ color: 'var(--text-primary)' }}>
                  Security Events
                </h2>
              </div>
              <div className="flex flex-wrap items-center gap-2.5 xl:-translate-x-4 xl:justify-end">
                <Filter size={15} style={{ color: 'var(--text-muted)' }} />
                <select
                  value={severityFilter}
                  onChange={(event) => setSeverityFilter(event.target.value)}
                  className="w-full rounded-lg px-4 py-2.5 text-sm outline-none sm:w-auto sm:min-w-[156px]"
                  style={{ border: '1px solid var(--border-color)', background: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                >
                  <option value="all">All severities</option>
                  <option value="critical">Critical</option>
                  <option value="warning">Warning</option>
                  <option value="info">Info</option>
                </select>
                <select
                  value={eventTypeFilter}
                  onChange={(event) => setEventTypeFilter(event.target.value)}
                  className="max-w-full w-full rounded-lg px-4 py-2.5 text-sm outline-none sm:w-auto sm:min-w-[184px]"
                  style={{ border: '1px solid var(--border-color)', background: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                >
                  <option value="all">All event types</option>
                  {eventTypeOptions.map((eventType) => (
                    <option key={eventType} value={eventType}>
                      {formatLabel(eventType)}
                    </option>
                  ))}
                </select>
                <label className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm" style={{ color: 'var(--text-secondary)' }}>
                  <input
                    type="checkbox"
                    checked={includeResolved}
                    onChange={(event) => setIncludeResolved(event.target.checked)}
                  />
                  Show resolved
                </label>
              </div>
            </div>
            <div className="h-3 md:h-4" />

            {error && (
              <div
                className="mb-4 rounded-xl px-4 py-3 text-sm"
                style={{
                  background: 'rgba(239,68,68,0.08)',
                  border: '1px solid rgba(239,68,68,0.18)',
                  color: '#ef4444',
                }}
              >
                {error}
              </div>
            )}

            <div className={`${securityEventsMaxHeightClass} overflow-y-auto`}>
              <div className="grid grid-cols-1 gap-4 px-3 sm:px-4 md:px-6 2xl:grid-cols-2">
                {filteredAlerts.map((alert, i) => {
                  const cfg = sevCfg[alert.severity] || sevCfg.info;
                  const statusCfg = statusStyles[alert.status] || statusStyles.active;
                  const Icon = cfg.icon;
                  const isBusy = busyAlertIds.has(alert.id);
                  const metadataEntries = extractAlertMetadataEntries(alert);
                  return (
                    <motion.div
                      key={alert.id}
                      className="relative min-h-[460px] min-w-0 overflow-visible rounded-xl px-5 pb-6 pt-3 sm:h-[320px] sm:min-h-0 sm:overflow-hidden sm:px-8 sm:pb-5 sm:pt-2 md:px-10 md:pb-6 md:pt-2"
                      style={{
                        background: 'var(--bg-secondary)',
                        border: `1px solid ${cfg.border}`,
                      }}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.05 }}
                      whileHover={{ boxShadow: `0 0 20px ${cfg.glow}` }}
                    >
                      <div className="flex h-full items-start px-4 pt-2 sm:px-4 sm:pt-1 md:px-5 md:pt-1">
                        <div className="flex h-full w-full items-start">
                          <motion.div
                            className="absolute left-3 top-5 flex h-10 w-10 items-center justify-center rounded-xl sm:left-4 sm:top-6 md:left-6 md:top-6"
                            style={{ background: cfg.bg }}
                            animate={alert.severity === 'critical' && alert.status === 'active' ? { scale: [1, 1.05, 1] } : {}}
                            transition={alert.severity === 'critical' && alert.status === 'active' ? { duration: 2, repeat: Infinity } : {}}
                          >
                            <Icon size={18} style={{ color: cfg.text }} />
                          </motion.div>
                          <div className="flex min-w-0 flex-1 self-center flex-col overflow-visible py-3 pl-[72px] pr-[144px] sm:overflow-hidden sm:py-2 sm:pl-[64px] sm:pr-[150px] md:pl-[72px]">
                            <div className="flex flex-col items-center gap-3">
                              <div className="min-w-0 text-center">
                                <h3 className="text-sm font-semibold break-words" style={{ color: 'var(--text-primary)' }}>{alert.title}</h3>
                                <p className="mt-1.5 text-xs" style={{ color: 'var(--text-muted)' }}>
                                  {alert.source_service} Â· {alert.event_type}
                                </p>
                              </div>
                              <span
                                className="absolute right-3 top-5 inline-flex min-h-[40px] min-w-[112px] items-center justify-center rounded-full px-4 py-2.5 text-center text-sm font-medium sm:right-4 sm:top-6 md:right-6 md:top-6"
                                style={{
                                  background: statusCfg.bg,
                                  color: statusCfg.color,
                                  border: `1px solid ${statusCfg.border}`,
                                }}
                              >
                                {alert.status}
                              </span>
                            </div>
                            <div className="mt-4 pb-8 pr-1 sm:min-h-0 sm:flex-1 sm:overflow-y-auto">
                              <p className="text-center text-xs leading-relaxed text-wrap-anywhere" style={{ color: 'var(--text-secondary)' }}>{alert.message}</p>
                              <div className="mt-4 flex flex-wrap items-center justify-center gap-4 text-xs" style={{ color: 'var(--text-muted)' }}>
                                <span className="flex items-center gap-1"><Clock size={10} />{formatDateTime(alert.last_seen_at)}</span>
                                <span>{alert.count} occurrence{alert.count > 1 ? 's' : ''}</span>
                                <span>Created {formatDateTime(alert.created_at)}</span>
                              </div>
                              {metadataEntries.length > 0 && (
                                <div className="mt-4 flex flex-wrap justify-center gap-2">
                                  {metadataEntries.map((entry) => (
                                    <span
                                      key={`${alert.id}-${entry.key}`}
                                      className="rounded-full px-5 py-3 text-xs"
                                      style={{
                                        background: 'rgba(148,163,184,0.08)',
                                        color: 'var(--text-secondary)',
                                        border: '1px solid rgba(148,163,184,0.15)',
                                      }}
                                    >
                                      {entry.label}: {entry.value}
                                    </span>
                                  ))}
                                </div>
                              )}
                            </div>
                            {alert.status === 'active' && (
                              <>
                                <div className="h-5 shrink-0" />
                                <div className="flex justify-center">
                                  <button
                                    type="button"
                                    onClick={() => handleResolve(alert.id)}
                                    disabled={isBusy}
                                    className="inline-flex h-14 w-[200px] items-center justify-center self-center gap-2 rounded-xl px-8 text-sm font-medium disabled:opacity-60"
                                    style={{
                                      background: 'rgba(16,185,129,0.1)',
                                      color: '#10b981',
                                      border: '1px solid rgba(16,185,129,0.2)',
                                    }}
                                  >
                                    <CheckCircle2 size={14} />
                                    {isBusy ? 'Resolving...' : 'Mark as resolved'}
                                  </button>
                                </div>
                              </>
                            )}
                          </div>
                        </div>
                      </div>
                    </motion.div>
                  );
                })}
              </div>
            </div>

            {!loading && filteredAlerts.length === 0 && (
              <div
                className="mt-6 rounded-xl px-5 py-10 text-center"
                style={{ border: '1px dashed var(--border-color)', color: 'var(--text-muted)' }}
              >
                No alerts match the current filters.
              </div>
            )}
          </div>

          <div className="pt-4">
            <div className="h-2 md:h-3" />
            <div className="flex items-center justify-between px-3">
              <h2 className="text-lg font-semibold font-display" style={{ color: 'var(--text-primary)' }}>Recent Alert Log</h2>
            </div>
            <div className="h-3 md:h-4" />
            <div
              className="overflow-hidden rounded-xl"
              style={{ border: '1px solid var(--border-color)', background: 'var(--bg-secondary)' }}
            >
              <div className="max-h-[560px] overflow-x-auto overflow-y-auto">
                <table className="w-full min-w-[640px] text-sm">
                  <thead>
                    <tr className="h-[72px]" style={{ background: 'var(--bg-tertiary)', borderBottom: '1px solid var(--border-color)' }}>
                      <th className="h-[72px] px-5 py-0 text-left align-middle font-semibold" style={{ color: 'var(--text-secondary)' }}>
                        <span className="relative left-4 inline-block">Last Seen</span>
                      </th>
                      <th className="h-[72px] px-5 py-0 text-left align-middle font-semibold" style={{ color: 'var(--text-secondary)' }}>Alert</th>
                      <th className="hidden h-[72px] px-5 py-0 text-left align-middle font-semibold md:table-cell" style={{ color: 'var(--text-secondary)' }}>Service</th>
                      <th className="hidden h-[72px] px-5 py-0 text-left align-middle font-semibold lg:table-cell" style={{ color: 'var(--text-secondary)' }}>Event Type</th>
                      <th className="h-[72px] px-5 py-0 text-left align-middle font-semibold" style={{ color: 'var(--text-secondary)' }}>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredAlerts.map((alert) => {
                      const st = statusStyles[alert.status] || statusStyles.active;
                      return (
                        <motion.tr
                          key={`row-${alert.id}`}
                          className="h-[84px]"
                          style={{ borderBottom: '1px solid var(--border-color)' }}
                          whileHover={{ background: 'rgba(139,92,246,0.03)' }}
                        >
                          <td className="h-[84px] px-5 py-0 align-middle text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
                            <span className="relative left-4 inline-block">{formatDateTime(alert.last_seen_at)}</span>
                          </td>
                          <td className="h-[84px] px-5 py-0 align-middle" style={{ color: 'var(--text-primary)' }}>{alert.title}</td>
                          <td className="hidden h-[84px] px-5 py-0 align-middle md:table-cell" style={{ color: 'var(--text-secondary)' }}>{alert.source_service}</td>
                          <td className="hidden h-[84px] px-5 py-0 align-middle lg:table-cell" style={{ color: 'var(--text-secondary)' }}>{alert.event_type}</td>
                          <td className="h-[84px] px-5 py-0 align-middle">
                            <span
                              className="inline-flex min-h-[40px] min-w-[112px] items-center justify-center rounded-full px-4 py-2.5 text-sm font-medium"
                              style={{ background: st.bg, color: st.color, border: `1px solid ${st.border}` }}
                            >
                              {alert.status}
                            </span>
                          </td>
                        </motion.tr>
                      );
                    })}
                    {!loading && filteredAlerts.length === 0 && (
                      <tr>
                        <td colSpan={5} className="px-5 py-12 text-center align-middle" style={{ color: 'var(--text-muted)' }}>
                          No alerts recorded yet.
                        </td>
                      </tr>
                    )}
                    {isInitialLoading && (
                      <tr>
                        <td colSpan={5} className="px-5 py-12 text-center align-middle" style={{ color: 'var(--text-muted)' }}>
                          Loading security alerts...
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>
    </AnimatedPage>
  );
}

