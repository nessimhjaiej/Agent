-- Run in the Supabase SQL editor.
-- Creates the public profile-images bucket and backfills expected auth.users metadata fields.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'profiles',
  'profiles',
  true,
  5242880,
  array['image/png', 'image/jpeg', 'image/webp', 'image/gif']
)
on conflict (id) do nothing;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'storage'
      and tablename = 'objects'
      and policyname = 'profiles_select_public'
  ) then
    create policy profiles_select_public
      on storage.objects
      for select
      to public
      using (bucket_id = 'profiles');
  end if;

  if not exists (
    select 1
    from pg_policies
    where schemaname = 'storage'
      and tablename = 'objects'
      and policyname = 'profiles_insert_own'
  ) then
    create policy profiles_insert_own
      on storage.objects
      for insert
      to authenticated
      with check (
        bucket_id = 'profiles'
        and split_part(name, '/', 1) = auth.uid()::text
      );
  end if;

  if not exists (
    select 1
    from pg_policies
    where schemaname = 'storage'
      and tablename = 'objects'
      and policyname = 'profiles_update_own'
  ) then
    create policy profiles_update_own
      on storage.objects
      for update
      to authenticated
      using (
        bucket_id = 'profiles'
        and split_part(name, '/', 1) = auth.uid()::text
      )
      with check (
        bucket_id = 'profiles'
        and split_part(name, '/', 1) = auth.uid()::text
      );
  end if;

  if not exists (
    select 1
    from pg_policies
    where schemaname = 'storage'
      and tablename = 'objects'
      and policyname = 'profiles_delete_own'
  ) then
    create policy profiles_delete_own
      on storage.objects
      for delete
      to authenticated
      using (
        bucket_id = 'profiles'
        and split_part(name, '/', 1) = auth.uid()::text
      );
  end if;
end $$;

update auth.users
set raw_user_meta_data =
  coalesce(raw_user_meta_data, '{}'::jsonb)
  || jsonb_build_object(
       'username',
       coalesce(
         nullif(raw_user_meta_data->>'username', ''),
         left(
           regexp_replace(split_part(coalesce(email, ''), '@', 1), '[^a-zA-Z0-9._-]', '_', 'g'),
           32
         ),
         'user'
       ),
       'phone_number',
       coalesce(raw_user_meta_data->>'phone_number', ''),
       'profile_picture',
       coalesce(raw_user_meta_data->>'profile_picture', ''),
       'invite_onboarding_completed',
       coalesce(
         (raw_user_meta_data->>'invite_onboarding_completed')::boolean,
         case
           when coalesce((raw_app_meta_data->>'invited_by_admin')::boolean, false) then false
           else true
         end
       )
     )
where true;
