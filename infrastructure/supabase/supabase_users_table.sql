-- Run in Supabase SQL editor.
-- Creates a public users table and keeps it two-way synced with auth.users.
--
-- Source of truth for role is auth.users.raw_user_meta_data->>'role'
-- (the SDK's user_metadata.role). public.users mirrors it.
--
-- Sync is bidirectional:
--   * auth.users  -> public.users  on INSERT or UPDATE of email / metadata
--   * public.users -> auth.users   on INSERT or UPDATE of role
-- Both directions only write when the value actually changed, so the two
-- triggers cannot bounce each other into an infinite loop.

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

-- auth.users -> public.users
-- Create or refresh the mirror row whenever a new auth user is created OR an
-- existing one's email / metadata changes (e.g. role edited in the dashboard,
-- or an invite promoting an existing user to admin).
create or replace function public.handle_auth_user_change()
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
    set email = excluded.email,
        -- keep existing role if the new metadata doesn't carry one,
        -- so unrelated auth updates can't silently downgrade an admin.
        role  = coalesce(new.raw_user_meta_data ->> 'role', public.users.role)
    where public.users.email is distinct from excluded.email
       or public.users.role  is distinct from
            coalesce(new.raw_user_meta_data ->> 'role', public.users.role);
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
drop trigger if exists on_auth_user_changed on auth.users;
-- `update of email, raw_user_meta_data` keeps the trigger from firing on every
-- login (which only touches last_sign_in_at) or on block/validate changes
-- (which touch raw_app_meta_data). It fires only when something we mirror moves.
create trigger on_auth_user_changed
after insert or update of email, raw_user_meta_data on auth.users
for each row execute function public.handle_auth_user_change();

-- public.users -> auth.users
-- Push role changes back into auth metadata, but only when it actually differs,
-- which breaks the sync loop with on_auth_user_changed above.
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
  where id = new.id
    and coalesce(raw_user_meta_data ->> 'role', '') is distinct from new.role;

  return new;
end;
$$;

drop trigger if exists trg_users_sync_role_to_auth on public.users;
create trigger trg_users_sync_role_to_auth
after insert or update of role on public.users
for each row execute function public.sync_role_to_auth_user();

-- Backfill existing auth users into public.users (email + role).
insert into public.users (id, email, role)
select
  u.id,
  coalesce(u.email, ''),
  coalesce(u.raw_user_meta_data ->> 'role', 'user') as role
from auth.users u
on conflict (id) do update
  set email = excluded.email,
      role  = excluded.role;

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
