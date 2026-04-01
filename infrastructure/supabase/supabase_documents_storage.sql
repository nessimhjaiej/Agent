-- Run in the Supabase SQL editor.
-- Creates the documents metadata table plus storage bucket/policies for per-user documents.

create extension if not exists pgcrypto;

create table if not exists public.documents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  original_name text not null,
  storage_path text not null unique,
  status text not null check (status in ('pending', 'validated', 'rejected')),
  embedded boolean not null default false,
  embedded_at timestamptz null,
  size_bytes bigint null,
  created_at timestamptz not null default now()
);

create index if not exists idx_documents_user_id on public.documents(user_id);
create index if not exists idx_documents_status on public.documents(status);
create index if not exists idx_documents_created_at on public.documents(created_at desc);

alter table public.documents enable row level security;

drop policy if exists docs_select_own on public.documents;
drop policy if exists docs_insert_own on public.documents;
drop policy if exists docs_update_own on public.documents;
drop policy if exists docs_delete_own on public.documents;

create policy docs_select_own
on public.documents
for select
to authenticated
using (auth.uid() = user_id);

create policy docs_insert_own
on public.documents
for insert
to authenticated
with check (auth.uid() = user_id);

create policy docs_update_own
on public.documents
for update
to authenticated
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

create policy docs_delete_own
on public.documents
for delete
to authenticated
using (auth.uid() = user_id);

insert into storage.buckets (id, name, public)
values ('documents', 'documents', false)
on conflict (id) do nothing;

drop policy if exists storage_docs_select_own on storage.objects;
drop policy if exists storage_docs_insert_own on storage.objects;
drop policy if exists storage_docs_update_own on storage.objects;
drop policy if exists storage_docs_delete_own on storage.objects;

create policy storage_docs_select_own
on storage.objects
for select
to authenticated
using (
  bucket_id = 'documents'
  and auth.uid()::text = (storage.foldername(name))[2]
);

create policy storage_docs_insert_own
on storage.objects
for insert
to authenticated
with check (
  bucket_id = 'documents'
  and auth.uid()::text = (storage.foldername(name))[2]
);

create policy storage_docs_update_own
on storage.objects
for update
to authenticated
using (
  bucket_id = 'documents'
  and auth.uid()::text = (storage.foldername(name))[2]
)
with check (
  bucket_id = 'documents'
  and auth.uid()::text = (storage.foldername(name))[2]
);

create policy storage_docs_delete_own
on storage.objects
for delete
to authenticated
using (
  bucket_id = 'documents'
  and auth.uid()::text = (storage.foldername(name))[2]
);
