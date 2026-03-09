-- Run in Supabase SQL editor.
create table if not exists public.documents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  original_name text not null,
  storage_path text not null unique,
  status text not null check (status in ('pending', 'validated', 'rejected')),
  embedded boolean not null default false,
  embedded_at timestamptz null,
  size_bytes bigint null,
  created_at timestamptz not null default now()
);

alter table public.documents enable row level security;

create policy if not exists "docs_select_own"
  on public.documents
  for select
  using (auth.uid() = user_id);

create policy if not exists "docs_insert_own"
  on public.documents
  for insert
  with check (auth.uid() = user_id);

create policy if not exists "docs_update_own"
  on public.documents
  for update
  using (auth.uid() = user_id);

create policy if not exists "docs_delete_own"
  on public.documents
  for delete
  using (auth.uid() = user_id);
