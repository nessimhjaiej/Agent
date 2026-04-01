# Supabase Infrastructure

Supabase is used in this project for:

- authentication
- user metadata
- storage
- document metadata integration

Setup assets in this folder:

- `supabase_users_table.sql` creates `public.users` and synchronizes role metadata with `auth.users`
- `supabase_audit_tables.sql` creates backend audit and login-attempt tables
- `supabase_documents_storage.sql` creates `public.documents` plus the private `documents` storage bucket and policies
- `supabase_profiles_storage.sql` creates the public `profiles` bucket, storage policies, and backfills expected profile metadata

Reference material:

- `scripts.txt` is a scratchpad/source dump of SQL snippets that were split into the reusable files above

Run the SQL file in the Supabase SQL editor before using auth and admin flows:

```sql
-- file: infrastructure/supabase/supabase_users_table.sql
```

Recommended order:

1. `supabase_users_table.sql`
2. `supabase_audit_tables.sql`
3. `supabase_documents_storage.sql`
4. `supabase_profiles_storage.sql`

You will also need to configure any additional project-specific tables or policies used by your local workflow.

