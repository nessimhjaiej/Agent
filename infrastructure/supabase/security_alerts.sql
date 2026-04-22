create table if not exists public.security_alerts (
  id uuid primary key default gen_random_uuid(),
  fingerprint text not null,
  event_type text not null,
  source_service text not null,
  severity text not null check (severity in ('info', 'warning', 'critical')),
  status text not null default 'active' check (status in ('active', 'resolved')),
  title text not null,
  message text not null,
  count integer not null default 1,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  last_seen_at timestamptz not null default timezone('utc', now())
);
create index if not exists idx_security_alerts_status_last_seen
  on public.security_alerts(status, last_seen_at desc);
create unique index if not exists idx_security_alerts_active_fingerprint
  on public.security_alerts(fingerprint)
  where status = 'active';
