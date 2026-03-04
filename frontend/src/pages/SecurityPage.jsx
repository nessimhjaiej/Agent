import { useState } from 'react';
import { motion } from 'framer-motion';
import { ShieldAlert, ShieldCheck, AlertTriangle, Activity, Clock, User, Eye, TrendingUp } from 'lucide-react';
import AnimatedPage from '../components/AnimatedPage';

const ALERTS = [
  { id: '1', type: 'Prompt Injection', severity: 'critical', count: 3, last: '2 min ago', desc: 'Detected attempts to override system prompt in user queries.' },
  { id: '2', type: 'Anomalous Query Volume', severity: 'warning', count: 1, last: '15 min ago', desc: 'Unusual spike in queries from a single IP address.' },
  { id: '3', type: 'Data Exfiltration Attempt', severity: 'critical', count: 1, last: '1 hour ago', desc: 'User attempted to extract full document content via repeated queries.' },
  { id: '4', type: 'Rate Limit Exceeded', severity: 'info', count: 12, last: '30 min ago', desc: 'Multiple users hit rate limits during peak usage.' },
];

const AUDIT_LOGS = [
  { id: '1', time: '2026-03-03 10:45:12', user: 'admin@company.com', action: 'Document Validated', target: 'GDPR_Regulation.pdf', status: 'success' },
  { id: '2', time: '2026-03-03 10:42:08', user: 'user@test.com', action: 'Query Submitted', target: 'RAG Pipeline', status: 'blocked' },
  { id: '3', time: '2026-03-03 10:38:55', user: 'admin@company.com', action: 'Re-embed Triggered', target: 'Vector Store', status: 'success' },
  { id: '4', time: '2026-03-03 10:35:00', user: 'analyst@corp.com', action: 'Query Submitted', target: 'RAG Pipeline', status: 'success' },
  { id: '5', time: '2026-03-03 10:30:22', user: 'unknown', action: 'Prompt Injection', target: 'Chat API', status: 'blocked' },
  { id: '6', time: '2026-03-03 10:25:10', user: 'admin@company.com', action: 'Document Uploaded', target: 'SOX_Compliance.pdf', status: 'success' },
  { id: '7', time: '2026-03-03 10:20:45', user: 'user2@test.com', action: 'Login Attempt', target: 'Auth Service', status: 'failed' },
  { id: '8', time: '2026-03-03 10:15:30', user: 'admin@company.com', action: 'Config Changed', target: 'Security Rules', status: 'success' },
];

const sevCfg = {
  critical: { bg: 'rgba(239,68,68,0.08)', glow: 'rgba(239,68,68,0.15)', text: '#ef4444', border: 'rgba(239,68,68,0.15)', icon: ShieldAlert },
  warning: { bg: 'rgba(245,158,11,0.08)', glow: 'rgba(245,158,11,0.15)', text: '#f59e0b', border: 'rgba(245,158,11,0.15)', icon: AlertTriangle },
  info: { bg: 'rgba(59,130,246,0.08)', glow: 'rgba(59,130,246,0.15)', text: '#3b82f6', border: 'rgba(59,130,246,0.15)', icon: Activity },
};

const statusStyles = {
  success: { bg: 'rgba(16,185,129,0.1)', color: '#10b981', border: 'rgba(16,185,129,0.2)' },
  blocked: { bg: 'rgba(239,68,68,0.1)', color: '#ef4444', border: 'rgba(239,68,68,0.2)' },
  failed: { bg: 'rgba(245,158,11,0.1)', color: '#f59e0b', border: 'rgba(245,158,11,0.2)' },
};

export default function SecurityPage() {
  const [logFilter, setLogFilter] = useState('all');
  const filteredLogs = AUDIT_LOGS.filter(l => logFilter === 'all' || l.status === logFilter);

  return (
    <AnimatedPage className="h-full overflow-y-auto p-8 space-y-8">
      {/* Summary Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: 'Threats Blocked', value: '24', sub: 'Last 24h', icon: ShieldCheck, color: '#10b981', glow: 'rgba(16,185,129,0.15)' },
          { label: 'Active Alerts', value: ALERTS.length, sub: 'Needs review', icon: ShieldAlert, color: '#ef4444', glow: 'rgba(239,68,68,0.15)' },
          { label: 'Total Queries', value: '1,247', sub: 'Today', icon: TrendingUp, color: 'var(--color-primary-400)', glow: 'rgba(139,92,246,0.15)' },
          { label: 'Audit Events', value: AUDIT_LOGS.length, sub: 'Recent', icon: Eye, color: '#3b82f6', glow: 'rgba(59,130,246,0.15)' },
        ].map((card, i) => (
          <motion.div
            key={i}
            className="rounded-xl p-5"
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
            <p className="text-2xl font-bold font-display" style={{ color: card.color }}>{card.value}</p>
            <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>{card.label} · {card.sub}</p>
          </motion.div>
        ))}
      </div>

      {/* Alerts */}
      <div>
        <h2 className="text-lg font-semibold font-display mb-4" style={{ color: 'var(--text-primary)' }}>Active Alerts</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {ALERTS.map((alert, i) => {
            const cfg = sevCfg[alert.severity];
            const Icon = cfg.icon;
            return (
              <motion.div
                key={alert.id}
                className="rounded-xl p-4"
                style={{
                  background: 'var(--bg-secondary)',
                  border: `1px solid ${cfg.border}`,
                }}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.06 }}
                whileHover={{
                  boxShadow: `0 0 20px ${cfg.glow}`,
                }}
              >
                <div className="flex items-start gap-3">
                  <motion.div
                    className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
                    style={{ background: cfg.bg }}
                    animate={alert.severity === 'critical' ? { scale: [1, 1.05, 1] } : {}}
                    transition={alert.severity === 'critical' ? { duration: 2, repeat: Infinity } : {}}
                  >
                    <Icon size={18} style={{ color: cfg.text }} />
                  </motion.div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{alert.type}</h3>
                      <span
                        className="text-xs font-medium px-2 py-0.5 rounded-full"
                        style={{
                          background: cfg.bg,
                          color: cfg.text,
                          border: `1px solid ${cfg.border}`,
                        }}
                      >
                        {alert.severity}
                      </span>
                    </div>
                    <p className="text-xs mt-1 leading-relaxed" style={{ color: 'var(--text-secondary)' }}>{alert.desc}</p>
                    <div className="flex items-center gap-4 mt-2 text-xs" style={{ color: 'var(--text-muted)' }}>
                      <span className="flex items-center gap-1"><Clock size={10} />{alert.last}</span>
                      <span>{alert.count} occurrence{alert.count > 1 ? 's' : ''}</span>
                    </div>
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>

      {/* Audit Logs */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold font-display" style={{ color: 'var(--text-primary)' }}>Audit Logs</h2>
          <select
            value={logFilter}
            onChange={e => setLogFilter(e.target.value)}
            className="px-3 py-1.5 rounded-lg text-xs outline-none"
            style={{ border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', color: 'var(--text-primary)' }}
          >
            <option value="all">All</option>
            <option value="success">Success</option>
            <option value="blocked">Blocked</option>
            <option value="failed">Failed</option>
          </select>
        </div>
        <div className="rounded-xl overflow-auto" style={{ border: '1px solid var(--border-color)' }}>
          <table className="w-full text-sm">
            <thead>
              <tr style={{ background: 'var(--bg-tertiary)', borderBottom: '1px solid var(--border-color)' }}>
                <th className="px-4 py-3 text-left font-semibold" style={{ color: 'var(--text-secondary)' }}>Time</th>
                <th className="px-4 py-3 text-left font-semibold" style={{ color: 'var(--text-secondary)' }}>User</th>
                <th className="px-4 py-3 text-left font-semibold hidden sm:table-cell" style={{ color: 'var(--text-secondary)' }}>Action</th>
                <th className="px-4 py-3 text-left font-semibold hidden md:table-cell" style={{ color: 'var(--text-secondary)' }}>Target</th>
                <th className="px-4 py-3 text-left font-semibold" style={{ color: 'var(--text-secondary)' }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {filteredLogs.map(log => {
                const st = statusStyles[log.status];
                return (
                  <motion.tr
                    key={log.id}
                    style={{ borderBottom: '1px solid var(--border-color)' }}
                    whileHover={{ background: 'rgba(139,92,246,0.03)' }}
                  >
                    <td className="px-4 py-3 text-xs font-mono" style={{ color: 'var(--text-muted)' }}>{log.time}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <User size={12} style={{ color: 'var(--text-muted)' }} />
                        <span style={{ color: 'var(--text-primary)' }}>{log.user}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 hidden sm:table-cell" style={{ color: 'var(--text-secondary)' }}>{log.action}</td>
                    <td className="px-4 py-3 hidden md:table-cell" style={{ color: 'var(--text-secondary)' }}>{log.target}</td>
                    <td className="px-4 py-3">
                      <span
                        className="text-xs font-medium px-2.5 py-0.5 rounded-full"
                        style={{ background: st.bg, color: st.color, border: `1px solid ${st.border}` }}
                      >
                        {log.status}
                      </span>
                    </td>
                  </motion.tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </AnimatedPage>
  );
}
