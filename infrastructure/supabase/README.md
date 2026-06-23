# Supabase Infrastructure

Supabase is the project's identity + storage + relational backend. It provides:

- authentication (Supabase Auth / GoTrue) — used through `auth-service`
- admin user management (validate / block / invite / delete)
- login-attempt tracking and audit logs
- security-alert persistence
- document metadata
- document and profile-picture storage

The browser never talks to Supabase Auth directly: `auth-service` owns all auth
operations using the **service-role** key. The browser keeps a thin Supabase
client only for Storage uploads (profile pictures) and Realtime (the documents
table), using the **anon** key.

## One-time setup (SQL only)

A brand-new Supabase project is fully provisioned by running four scripts — no
manual table or bucket creation is needed. Open **SQL Editor** and run them in
this order (each is safe to re-run):

```text
1. infrastructure/supabase/supabase_users_table.sql
2. infrastructure/supabase/app_tables.sql
3. infrastructure/supabase/security_alerts.sql
4. infrastructure/supabase/storage_buckets.sql
```

What each script creates:

| Script | Creates |
|--------|---------|
| `supabase_users_table.sql` | `public.users` + two-way role-sync triggers with `auth.users` (so `role` stays mirrored) |
| `app_tables.sql` | `public.documents`, `public.audit_logs`, `public.login_attempts` (+ indexes + RLS) |
| `security_alerts.sql` | `public.security_alerts` (+ dedup unique index on active fingerprints) |
| `storage_buckets.sql` | the `documents` (private) and `profiles` (public) Storage buckets + their access policies |

After running them, the Storage buckets already exist:

- `documents` — **private**. Files live under
  `pending/<user_id>/<filename>`, `validated/<user_id>/<filename>`,
  `rejected/<user_id>/<filename>`. Accessed only via `ingestion-service` with the
  service-role key, so it needs no client policies.
- `profiles` — **public**. Profile pictures live under `<user_id>/<filename>`.
  The browser uploads here directly, so `storage_buckets.sql` adds policies that
  let a user write only inside their own folder.

## Keys

| Where | Key | Env var |
|-------|-----|---------|
| Backend (auth/ingestion/embedding/security) | **service-role** | `AUTH_SUPABASE_KEY` (and `SECURITY_SUPABASE_KEY`) |
| Frontend (Storage + Realtime only) | **anon / public** | `VITE_SUPABASE_ANON_KEY` |

> ⚠️ `AUTH_SUPABASE_KEY` must be the **service-role** key (a full admin JWT, found
> under Project Settings → API). The backend performs admin user actions and
> writes RLS-protected tables (`login_attempts`, `audit_logs`); an anon or
> restricted key makes login and user management fail.

## Creating the first admin

After someone signs up (or you create a user), promote them to admin by setting
the role on `public.users` — the sync trigger pushes it into `auth.users`
automatically:

```sql
update public.users set role = 'admin' where email = 'you@example.com';
```

Then sign in again. Admin screens and admin APIs require `role = 'admin'`.
