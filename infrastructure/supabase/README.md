# Supabase Infrastructure

Supabase is used for:

- authentication
- admin user management
- login attempt tracking
- audit logs
- security alert persistence
- document metadata
- document and profile storage

## Required SQL

Run these files in the Supabase SQL Editor in this order:

```text
infrastructure/supabase/supabase_users_table.sql
infrastructure/supabase/app_tables.sql
infrastructure/supabase/security_alerts.sql
```

What they create:

- `supabase_users_table.sql`: `public.users` plus role synchronization triggers.
- `app_tables.sql`: `public.documents`, `public.audit_logs`, and `public.login_attempts`.
- `security_alerts.sql`: `public.security_alerts`.

## Required Storage Buckets

Create these buckets in Supabase Storage:

- `documents`: private
- `profiles`: public by default for current profile image URLs

The document workflow stores files under:

```text
pending/<user_id>/<filename>
validated/<user_id>/<filename>
rejected/<user_id>/<filename>
```

The backend should use the Supabase service-role key through `AUTH_SUPABASE_KEY`; the frontend should use the anon key through `VITE_SUPABASE_ANON_KEY`.
