-- Run in Supabase SQL editor.
-- Creates a public users table and keeps role changes synced to auth.users metadata.

create extension if not exists pgcrypto;

create table if not exists public.users (
  id uuid primary key references auth.users (id) on delete cascade,
  email text not null unique,
  role text not null default 'user' check (role in ('user', 'admin')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_users_set_updated_at on public.users;
create trigger trg_users_set_updated_at
before update on public.users
for each row execute function public.set_updated_at();

-- Create/refresh a public.users row whenever a new auth user is created.
create or replace function public.handle_new_auth_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.users (id, email, role)
  values (
    new.id,
    coalesce(new.email, ''),
    coalesce(new.raw_user_meta_data ->> 'role', 'user')
  )
  on conflict (id) do update
    set email = excluded.email;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
after insert on auth.users
for each row execute function public.handle_new_auth_user();

-- Keep auth.users role metadata aligned when public.users.role changes.
create or replace function public.sync_role_to_auth_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  update auth.users
  set raw_user_meta_data = jsonb_set(
    coalesce(raw_user_meta_data, '{}'::jsonb),
    '{role}',
    to_jsonb(new.role::text),
    true
  )
  where id = new.id;

  return new;
end;
$$;

drop trigger if exists trg_users_sync_role_to_auth on public.users;
create trigger trg_users_sync_role_to_auth
after insert or update of role on public.users
for each row execute function public.sync_role_to_auth_user();

-- Backfill existing auth users into public.users.
insert into public.users (id, email, role)
select
  u.id,
  coalesce(u.email, ''),
  coalesce(u.raw_user_meta_data ->> 'role', 'user') as role
from auth.users u
on conflict (id) do update
  set email = excluded.email;

-- Optional: strict client-side access.
alter table public.users enable row level security;

drop policy if exists users_no_client_access on public.users;
create policy users_no_client_access
on public.users
for all
using (false)
with check (false);

-- Promote a user to admin (example):
-- update public.users set role = 'admin' where email = 'user@example.com';
