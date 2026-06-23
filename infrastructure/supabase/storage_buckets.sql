-- Run in the Supabase SQL editor (after the other scripts).
-- Creates the Storage buckets and access policies the app needs, so you do NOT
-- have to create buckets by hand in the Supabase dashboard.
--
-- Buckets:
--   * documents : PRIVATE. Holds uploaded PDFs under
--                 pending|validated|rejected/<user_id>/<filename>.
--                 All access goes through ingestion-service using the Supabase
--                 service-role key, which bypasses Storage RLS — so this bucket
--                 needs no client policies for the current app to work.
--   * profiles  : PUBLIC. Holds profile pictures under <user_id>/<file>.
--                 The browser uploads these directly with the anon key + the
--                 signed-in user's session, so this bucket DOES need RLS
--                 policies that let a user manage only their own folder.

-- ── Buckets ────────────────────────────────────────────────────────────────
insert into storage.buckets (id, name, public)
values ('documents', 'documents', false)
on conflict (id) do update set public = false;

insert into storage.buckets (id, name, public)
values ('profiles', 'profiles', true)
on conflict (id) do update set public = true;

-- ── profiles: public read ──────────────────────────────────────────────────
-- The bucket is public, but an explicit SELECT policy keeps behavior the same
-- even if the bucket is later flipped to private.
drop policy if exists "profiles_public_read" on storage.objects;
create policy "profiles_public_read"
on storage.objects
for select
to public
using (bucket_id = 'profiles');

-- ── profiles: a user can write only inside their own <user_id>/ folder ───────
-- storage.foldername(name) splits the object path into folders; element [1] is
-- the first folder, which the frontend sets to the user's id.
drop policy if exists "profiles_insert_own" on storage.objects;
create policy "profiles_insert_own"
on storage.objects
for insert
to authenticated
with check (
  bucket_id = 'profiles'
  and (storage.foldername(name))[1] = auth.uid()::text
);

drop policy if exists "profiles_update_own" on storage.objects;
create policy "profiles_update_own"
on storage.objects
for update
to authenticated
using (
  bucket_id = 'profiles'
  and (storage.foldername(name))[1] = auth.uid()::text
)
with check (
  bucket_id = 'profiles'
  and (storage.foldername(name))[1] = auth.uid()::text
);

drop policy if exists "profiles_delete_own" on storage.objects;
create policy "profiles_delete_own"
on storage.objects
for delete
to authenticated
using (
  bucket_id = 'profiles'
  and (storage.foldername(name))[1] = auth.uid()::text
);

-- Note: no policies are created for the `documents` bucket on purpose. The
-- backend reaches it with the service-role key (which bypasses RLS). If you
-- ever switch to uploading documents directly from the browser with the anon
-- key, add owner-scoped policies for `documents` mirroring the ones above.
