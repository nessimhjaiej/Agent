-- Run in the Supabase SQL editor.
-- Application tables required by auth-service, ingestion-service, and embedding-service.

create extension if not exists pgcrypto;

create table if not exists public.documents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  original_name text not null,
  storage_path text not null unique,
  status text not null default 'pending'
    check (status in ('pending', 'validated', 'rejected')),
  embedded boolean not null default false,
  size_bytes bigint not null default 0,
  created_at timestamptz not null default timezone('utc', now()),
  embedded_at timestamptz
);

create index if not exists idx_documents_user_created_at
  on public.documents (user_id, created_at desc);

create index if not exists idx_documents_status_embedded
  on public.documents (status, embedded);

create table if not exists public.audit_logs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users (id) on delete set null,
  action text not null,
  details jsonb not null default '{}'::jsonb,
  timestamp timestamptz not null default timezone('utc', now())
);

create index if not exists idx_audit_logs_user_timestamp
  on public.audit_logs (user_id, timestamp desc);

create table if not exists public.login_attempts (
  id uuid primary key default gen_random_uuid(),
  email text not null,
  success boolean not null,
  timestamp timestamptz not null default timezone('utc', now())
);

create index if not exists idx_login_attempts_email_timestamp
  on public.login_attempts (lower(email), timestamp desc);

create index if not exists idx_login_attempts_timestamp
  on public.login_attempts (timestamp desc);

alter table public.documents enable row level security;
alter table public.audit_logs enable row level security;
alter table public.login_attempts enable row level security;

drop policy if exists documents_select_own on public.documents;
create policy documents_select_own
on public.documents
for select
to authenticated
using (auth.uid() = user_id);

drop policy if exists documents_insert_own on public.documents;
create policy documents_insert_own
on public.documents
for insert
to authenticated
with check (auth.uid() = user_id);

drop policy if exists documents_update_own on public.documents;
create policy documents_update_own
on public.documents
for update
to authenticated
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

drop policy if exists documents_delete_own on public.documents;
create policy documents_delete_own
on public.documents
for delete
to authenticated
using (auth.uid() = user_id);

drop policy if exists audit_logs_no_client_access on public.audit_logs;
create policy audit_logs_no_client_access
on public.audit_logs
for all
using (false)
with check (false);

drop policy if exists login_attempts_no_client_access on public.login_attempts;
create policy login_attempts_no_client_access
on public.login_attempts
for all
using (false)
with check (false);
