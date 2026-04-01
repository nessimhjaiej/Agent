-- Run in the Supabase SQL editor.
-- Creates backend-oriented audit and login-attempt tables used by admin/security flows.

create extension if not exists pgcrypto;

create table if not exists public.audit_logs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  action text not null,
  details jsonb,
  timestamp timestamptz not null default now()
);

create table if not exists public.login_attempts (
  id uuid primary key default gen_random_uuid(),
  email text not null,
  success boolean not null,
  timestamp timestamptz not null default now()
);

create index if not exists idx_audit_logs_user_id on public.audit_logs(user_id);
create index if not exists idx_login_attempts_email on public.login_attempts(email);
create index if not exists idx_login_attempts_timestamp on public.login_attempts(timestamp desc);

alter table public.audit_logs disable row level security;
alter table public.login_attempts disable row level security;
