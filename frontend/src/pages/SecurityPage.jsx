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
  const preferredOrder = ['email', 'role', 'client_ip', 'path', 'method', 'reason', 'user_id'];

  const orderedKeys = [
    ...preferredOrder.filter((key) => metadata[key]),
    ...Object.keys(metadata).filter((key) => !preferredOrder.includes(key) && metadata[key]),
  ];

  return orderedKeys.map((key) => ({
    key,
    label: formatLabel(key),
    value: String(metadata[key]),
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
    <AnimatedPage className="h-full min-h-0 overflow-hidden p-2 sm:p-3 md:p-5 lg:p-6">
      <div className="h-full overflow-y-auto pr-1">
      <div className="w-full max-w-[1560px] mx-auto space-y-4 md:space-y-5">
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 md:gap-4">
        {[
          { label: 'Active Alerts', value: summary.active_alerts, sub: 'Needs review', icon: ShieldAlert, color: '#ef4444', glow: 'rgba(239,68,68,0.15)' },
          { label: 'Critical Alerts', value: summary.critical_alerts, sub: 'Highest priority', icon: AlertTriangle, color: '#f59e0b', glow: 'rgba(245,158,11,0.15)' },
          { label: 'Warning Alerts', value: summary.warning_alerts, sub: 'Watch closely', icon: TrendingUp, color: 'var(--color-primary-400)', glow: 'rgba(139,92,246,0.15)' },
          { label: 'Info Alerts', value: summary.info_alerts, sub: 'Telemetry', icon: ShieldCheck, color: '#10b981', glow: 'rgba(16,185,129,0.15)' },
        ].map((card, i) => (
          <motion.div
            key={card.label}
            className="rounded-xl p-4 md:p-5 min-w-0"
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
            <div className="flex items-center justify-between mb-3">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: card.glow }}
              >
                <card.icon size={20} style={{ color: card.color }} />
              </div>
            </div>
            <p className="text-xl md:text-2xl font-bold font-display break-words" style={{ color: card.color }}>{card.value}</p>
            <p className="text-[11px] md:text-xs mt-1 leading-relaxed" style={{ color: 'var(--text-muted)' }}>{card.label} · {card.sub}</p>
          </motion.div>
        ))}
      </div>

      <div>
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3 mb-4">
          <div className="min-w-0">
            <h2 className="text-lg font-semibold font-display" style={{ color: 'var(--text-primary)' }}>
              Login Attempts
            </h2>
          </div>
          {!loginAttemptsSummary.enabled && (
            <span
              className="text-xs font-medium px-2.5 py-1 rounded-full"
              style={{
                background: 'rgba(245,158,11,0.1)',
                color: '#f59e0b',
                border: '1px solid rgba(245,158,11,0.2)',
              }}
            >
              Supabase read disabled
            </span>
          )}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 md:gap-4">
          {[
            { label: 'Total Attempts', value: loginAttemptsSummary.total_attempts, color: '#3b82f6', glow: 'rgba(59,130,246,0.15)', icon: Activity },
            { label: 'Failed Attempts', value: loginAttemptsSummary.failed_attempts, color: '#ef4444', glow: 'rgba(239,68,68,0.15)', icon: ShieldAlert },
            { label: 'Successful Attempts', value: loginAttemptsSummary.successful_attempts, color: '#10b981', glow: 'rgba(16,185,129,0.15)', icon: ShieldCheck },
            { label: 'Unique Emails', value: loginAttemptsSummary.unique_emails, color: '#f59e0b', glow: 'rgba(245,158,11,0.15)', icon: TrendingUp },
          ].map((card) => (
            <div
              key={card.label}
              className="rounded-xl p-4 md:p-5 min-w-0"
              style={{
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border-color)',
                boxShadow: `0 0 25px ${card.glow}`,
              }}
            >
              <div className="flex items-center justify-between mb-3">
                <div
                  className="w-10 h-10 rounded-xl flex items-center justify-center"
                  style={{ background: card.glow }}
                >
                  <card.icon size={20} style={{ color: card.color }} />
                </div>
              </div>
              <p className="text-xl md:text-2xl font-bold font-display break-words" style={{ color: card.color }}>{card.value}</p>
              <p className="text-[11px] md:text-xs mt-1 leading-relaxed" style={{ color: 'var(--text-muted)' }}>{card.label}</p>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-3 md:gap-4 mt-4">
          <div
            className="rounded-xl overflow-hidden"
            style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)' }}
          >
            <div className="px-4 py-3" style={{ borderBottom: '1px solid var(--border-color)' }}>
              <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                Recent Failed Attempts
              </h3>
            </div>
            <div className="max-h-[260px] md:max-h-[300px] overflow-auto">
              {loginAttemptsSummary.recent_failed_attempts.length > 0 ? loginAttemptsSummary.recent_failed_attempts.map((attempt, index) => (
                <div
                  key={`${attempt.email}-${attempt.timestamp}-${index}`}
                  className="px-4 py-3"
                  style={{ borderBottom: '1px solid var(--border-color)' }}
                >
                  <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                    {attempt.email || 'unknown'}
                  </p>
                  <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
                    {formatDateTime(attempt.timestamp)}
                  </p>
                </div>
              )) : (
                <div className="px-4 py-8 text-center text-sm" style={{ color: 'var(--text-muted)' }}>
                  No failed attempts in the selected window.
                </div>
              )}
            </div>
          </div>

          <div
            className="rounded-xl overflow-hidden"
            style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)' }}
          >
            <div className="px-4 py-3" style={{ borderBottom: '1px solid var(--border-color)' }}>
              <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                Top Targeted Accounts
              </h3>
            </div>
            <div className="max-h-[260px] md:max-h-[300px] overflow-auto">
              {loginAttemptsSummary.top_targeted_accounts.length > 0 ? loginAttemptsSummary.top_targeted_accounts.map((item) => (
                <div
                  key={item.email}
                  className="px-4 py-3 flex items-center justify-between"
                  style={{ borderBottom: '1px solid var(--border-color)' }}
                >
                  <p className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>
                    {item.email}
                  </p>
                  <span
                    className="text-xs font-medium px-2.5 py-1 rounded-full"
                    style={{
                      background: 'rgba(239,68,68,0.1)',
                      color: '#ef4444',
                      border: '1px solid rgba(239,68,68,0.2)',
                    }}
                  >
                    {item.failed_attempts} failed
                  </span>
                </div>
              )) : (
                <div className="px-4 py-8 text-center text-sm" style={{ color: 'var(--text-muted)' }}>
                  No targeted accounts detected.
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <div
        className="rounded-xl p-4 md:p-5 min-w-0"
        style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)' }}
      >
          <div className="flex flex-col xl:flex-row xl:items-start xl:justify-between gap-3 mb-4">
            <div className="min-w-0">
              <h2 className="text-lg font-semibold font-display" style={{ color: 'var(--text-primary)' }}>
                Security Events
              </h2>
              <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
                Real-time alerts emitted by the backend security checks.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2 xl:justify-end">
              <Filter size={15} style={{ color: 'var(--text-muted)' }} />
              <select
                value={severityFilter}
                onChange={(event) => setSeverityFilter(event.target.value)}
                className="px-3 py-1.5 rounded-lg text-xs outline-none w-full sm:w-auto sm:min-w-[132px]"
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
                className="px-3 py-1.5 rounded-lg text-xs outline-none w-full sm:w-auto sm:min-w-[158px] max-w-full"
                style={{ border: '1px solid var(--border-color)', background: 'var(--bg-primary)', color: 'var(--text-primary)' }}
              >
                <option value="all">All event types</option>
                {eventTypeOptions.map((eventType) => (
                  <option key={eventType} value={eventType}>
                    {formatLabel(eventType)}
                  </option>
                ))}
              </select>
              <label className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
                <input
                  type="checkbox"
                  checked={includeResolved}
                  onChange={(event) => setIncludeResolved(event.target.checked)}
                />
                Show resolved
              </label>
            </div>
          </div>

          {error && (
            <div
              className="rounded-xl px-4 py-3 text-sm mb-4"
              style={{
                background: 'rgba(239,68,68,0.08)',
                border: '1px solid rgba(239,68,68,0.18)',
                color: '#ef4444',
              }}
            >
              {error}
            </div>
          )}

          <div className="grid grid-cols-1 2xl:grid-cols-2 gap-3">
            {filteredAlerts.map((alert, i) => {
              const cfg = sevCfg[alert.severity] || sevCfg.info;
              const statusCfg = statusStyles[alert.status] || statusStyles.active;
              const Icon = cfg.icon;
              const isBusy = busyAlertIds.has(alert.id);
              const metadataEntries = extractAlertMetadataEntries(alert);
              return (
                <motion.div
                  key={alert.id}
                  className="rounded-xl p-4 min-w-0"
                  style={{
                    background: 'var(--bg-secondary)',
                    border: `1px solid ${cfg.border}`,
                  }}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.05 }}
                  whileHover={{ boxShadow: `0 0 20px ${cfg.glow}` }}
                >
                  <div className="flex items-start gap-3">
                    <motion.div
                      className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
                      style={{ background: cfg.bg }}
                      animate={alert.severity === 'critical' && alert.status === 'active' ? { scale: [1, 1.05, 1] } : {}}
                      transition={alert.severity === 'critical' && alert.status === 'active' ? { duration: 2, repeat: Infinity } : {}}
                    >
                      <Icon size={18} style={{ color: cfg.text }} />
                    </motion.div>
                    <div className="flex-1 min-w-0">
                      <div className="flex flex-col sm:flex-row items-start sm:items-start justify-between gap-2">
                        <div className="min-w-0">
                          <h3 className="text-sm font-semibold break-words" style={{ color: 'var(--text-primary)' }}>{alert.title}</h3>
                          <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
                            {alert.source_service} · {alert.event_type}
                          </p>
                        </div>
                        <span
                          className="text-xs font-medium px-2 py-0.5 rounded-full"
                          style={{
                            background: statusCfg.bg,
                            color: statusCfg.color,
                            border: `1px solid ${statusCfg.border}`,
                          }}
                        >
                          {alert.status}
                        </span>
                      </div>
                      <p className="text-xs mt-3 leading-relaxed text-wrap-anywhere" style={{ color: 'var(--text-secondary)' }}>{alert.message}</p>
                      <div className="flex items-center gap-4 mt-3 text-xs flex-wrap" style={{ color: 'var(--text-muted)' }}>
                        <span className="flex items-center gap-1"><Clock size={10} />{formatDateTime(alert.last_seen_at)}</span>
                        <span>{alert.count} occurrence{alert.count > 1 ? 's' : ''}</span>
                        <span>Created {formatDateTime(alert.created_at)}</span>
                      </div>
                      {metadataEntries.length > 0 && (
                        <div className="mt-3 flex flex-wrap gap-2">
                          {metadataEntries.map((entry) => (
                            <span
                              key={`${alert.id}-${entry.key}`}
                              className="text-[11px] px-2.5 py-1 rounded-full"
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
                      {alert.status === 'active' && (
                        <button
                          type="button"
                          onClick={() => handleResolve(alert.id)}
                          disabled={isBusy}
                          className="mt-4 inline-flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-medium disabled:opacity-60"
                          style={{
                            background: 'rgba(16,185,129,0.1)',
                            color: '#10b981',
                            border: '1px solid rgba(16,185,129,0.2)',
                          }}
                        >
                          <CheckCircle2 size={14} />
                          {isBusy ? 'Resolving...' : 'Mark as resolved'}
                        </button>
                      )}
                    </div>
                  </div>
                </motion.div>
              );
            })}
          </div>

          {!loading && filteredAlerts.length === 0 && (
            <div
              className="rounded-xl px-4 py-10 mt-3 text-center"
              style={{ border: '1px dashed var(--border-color)', color: 'var(--text-muted)' }}
            >
              No alerts match the current filters.
            </div>
          )}
      </div>

      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold font-display" style={{ color: 'var(--text-primary)' }}>Recent Alert Log</h2>
        </div>
        <div className="rounded-xl safe-scroll-x" style={{ border: '1px solid var(--border-color)' }}>
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr style={{ background: 'var(--bg-tertiary)', borderBottom: '1px solid var(--border-color)' }}>
                <th className="px-4 py-3 text-left font-semibold" style={{ color: 'var(--text-secondary)' }}>Last Seen</th>
                <th className="px-4 py-3 text-left font-semibold" style={{ color: 'var(--text-secondary)' }}>Alert</th>
                <th className="px-4 py-3 text-left font-semibold hidden md:table-cell" style={{ color: 'var(--text-secondary)' }}>Service</th>
                <th className="px-4 py-3 text-left font-semibold hidden lg:table-cell" style={{ color: 'var(--text-secondary)' }}>Event Type</th>
                <th className="px-4 py-3 text-left font-semibold" style={{ color: 'var(--text-secondary)' }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {filteredAlerts.map((alert) => {
                const st = statusStyles[alert.status] || statusStyles.active;
                return (
                  <motion.tr
                    key={`row-${alert.id}`}
                    style={{ borderBottom: '1px solid var(--border-color)' }}
                    whileHover={{ background: 'rgba(139,92,246,0.03)' }}
                  >
                    <td className="px-4 py-3 text-xs font-mono" style={{ color: 'var(--text-muted)' }}>{formatDateTime(alert.last_seen_at)}</td>
                    <td className="px-4 py-3" style={{ color: 'var(--text-primary)' }}>{alert.title}</td>
                    <td className="px-4 py-3 hidden md:table-cell" style={{ color: 'var(--text-secondary)' }}>{alert.source_service}</td>
                    <td className="px-4 py-3 hidden lg:table-cell" style={{ color: 'var(--text-secondary)' }}>{alert.event_type}</td>
                    <td className="px-4 py-3">
                      <span
                        className="text-xs font-medium px-2.5 py-0.5 rounded-full"
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
                  <td colSpan={5} className="px-4 py-10 text-center" style={{ color: 'var(--text-muted)' }}>
                    No alerts recorded yet.
                  </td>
                </tr>
              )}
              {loading && (
                <tr>
                  <td colSpan={5} className="px-4 py-10 text-center" style={{ color: 'var(--text-muted)' }}>
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
    </AnimatedPage>
  );
}
