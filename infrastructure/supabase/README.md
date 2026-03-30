# Supabase Infrastructure

Supabase is used in this project for:

- authentication
- user metadata
- storage
- document metadata integration

Setup assets in this folder:

- `supabase_users_table.sql` creates `public.users` and synchronizes role metadata with `auth.users`

Run the SQL file in the Supabase SQL editor before using auth and admin flows:

```sql
-- file: infrastructure/supabase/supabase_users_table.sql
```

You will also need to configure the required storage bucket and any additional application tables used by your local workflow.

