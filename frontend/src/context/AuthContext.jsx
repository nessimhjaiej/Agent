import { createContext, useContext, useState, useEffect, useRef } from 'react';
import { createClient } from '@supabase/supabase-js';
import { isPasswordStrong, PASSWORD_POLICY_MESSAGE } from '../utils/passwordPolicy';
import {
  loginWithPassword,
  signupRequest,
  refreshSessionRequest,
  fetchCurrentUser,
  updateProfileRequest,
  updatePasswordRequest,
  logoutRequest,
  setUnauthorizedHandler,
  setTokenRefresher,
} from '../config/api';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;
const profileBucket = import.meta.env.VITE_SUPABASE_PROFILE_BUCKET || 'profiles';

// Auth is owned by the auth-service. This client is kept ONLY for non-auth
// features (Storage uploads + Realtime) and is fed a session via setSession;
// it never manages or refreshes the session itself.
const supabase =
  supabaseUrl && supabaseAnonKey
    ? createClient(supabaseUrl, supabaseAnonKey, {
        auth: {
          autoRefreshToken: false,
          persistSession: false,
          // Keep URL detection so an invite/recovery link's session is parsed;
          // bootstrap adopts it into the auth-service-owned token store.
          detectSessionInUrl: true,
        },
      })
    : null;

const AuthContext = createContext(null);
const AUTH_CACHE_KEY = 'agent.auth.cache.v1';
const AUTH_TOKENS_KEY = 'agent.auth.tokens.v1';
const AUTH_SIGN_OUT_EVENT_KEY = 'agent.auth.signout.v1';
const AUTH_BROADCAST_CHANNEL = 'agent-auth';
const TOKEN_REFRESH_SKEW_MS = 60_000;
const BLOCKED_POLL_INTERVAL_MS = 60_000;

function deriveUsernameFromEmail(email) {
  const localPart = (email || '').split('@')[0].trim().toLowerCase();
  if (!localPart) return 'user';
  return localPart.replace(/[^a-z0-9._-]/g, '_').slice(0, 32) || 'user';
}

function getAccountFlags(currentUser) {
  const role = currentUser?.user_metadata?.role || 'user';
  const appMetadata = currentUser?.app_metadata || {};
  const blocked = appMetadata.account_blocked === true;
  const validated = role === 'admin' || appMetadata.account_validated !== false;
  const username = (currentUser?.user_metadata?.username || '').trim();
  const invited = appMetadata.invited_by_admin === true;
  const inviteOnboardingCompleted =
    currentUser?.user_metadata?.invite_onboarding_completed === true;
  const requireInviteOnboarding = invited && !inviteOnboardingCompleted;
  return { role, blocked, validated, username, requireInviteOnboarding };
}

function readStoredTokens() {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(AUTH_TOKENS_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.access_token || !parsed?.refresh_token) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }) {
  const readCachedAuthState = () => {
    if (typeof window === 'undefined') {
      return { user: null, userRole: null, requireInviteOnboarding: false };
    }
    try {
      const rawValue = window.localStorage.getItem(AUTH_CACHE_KEY);
      if (!rawValue) {
        return { user: null, userRole: null, requireInviteOnboarding: false };
      }
      const parsed = JSON.parse(rawValue);
      const cachedUser = parsed?.user ?? null;
      return {
        user: cachedUser,
        userRole: parsed?.userRole || cachedUser?.user_metadata?.role || null,
        requireInviteOnboarding: parsed?.requireInviteOnboarding === true,
      };
    } catch {
      return { user: null, userRole: null, requireInviteOnboarding: false };
    }
  };

  const cachedAuthState = readCachedAuthState();
  const [user, setUser] = useState(cachedAuthState.user);
  const [userRole, setUserRole] = useState(cachedAuthState.userRole);
  const [requireInviteOnboarding, setRequireInviteOnboarding] = useState(cachedAuthState.requireInviteOnboarding);
  const [authRefreshKey, setAuthRefreshKey] = useState(0);
  const [loading, setLoading] = useState(!cachedAuthState.user);
  const latestUserRef = useRef(cachedAuthState.user);
  const tokensRef = useRef(readStoredTokens());
  const authBroadcastRef = useRef(null);
  // Holds the single in-flight refresh promise so concurrent callers share one
  // refresh (and one refresh-token rotation) instead of racing each other.
  const refreshInFlightRef = useRef(null);

  const persistUserState = (currentUser, role, requiresOnboarding) => {
    if (typeof window === 'undefined') return;
    try {
      window.localStorage.setItem(
        AUTH_CACHE_KEY,
        JSON.stringify({ user: currentUser, userRole: role, requireInviteOnboarding: requiresOnboarding })
      );
    } catch {
      // Ignore storage failures and keep in-memory auth state.
    }
  };

  const clearPersistedUserState = () => {
    if (typeof window === 'undefined') return;
    try {
      window.localStorage.removeItem(AUTH_CACHE_KEY);
    } catch {
      // Ignore storage failures.
    }
  };

  // ── Token store (frontend owns the tokens; auth-service mints them) ─────
  const storeTokens = (session) => {
    const accessToken = session?.access_token || '';
    const refreshToken = session?.refresh_token || '';
    if (!accessToken || !refreshToken) return null;
    const expiresInMs = (Number(session?.expires_in) || 3600) * 1000;
    const tokens = {
      access_token: accessToken,
      refresh_token: refreshToken,
      expires_at: Date.now() + expiresInMs,
    };
    tokensRef.current = tokens;
    if (typeof window !== 'undefined') {
      try {
        window.localStorage.setItem(AUTH_TOKENS_KEY, JSON.stringify(tokens));
      } catch {
        // Ignore storage failures and keep tokens in memory.
      }
    }
    // Feed the thin client so Storage + Realtime have an authenticated context.
    seedThinClient(tokens);
    return tokens;
  };

  const clearTokens = () => {
    tokensRef.current = null;
    if (typeof window === 'undefined') return;
    try {
      window.localStorage.removeItem(AUTH_TOKENS_KEY);
    } catch {
      // Ignore storage failures.
    }
  };

  const seedThinClient = (tokens) => {
    if (!supabase || !tokens?.access_token) return;
    // Never seed an expired access token: supabase-js's setSession refreshes it
    // immediately (even with autoRefreshToken off), rotating the refresh token
    // out from under the auth-service-owned refresh. Seed only fresh tokens;
    // an expired one gets re-seeded right after getAccessToken refreshes.
    if (tokens.expires_at && tokens.expires_at <= Date.now()) return;
    // Fire-and-forget; if it fails, Realtime/Storage are simply unauthenticated.
    Promise.resolve(
      supabase.auth.setSession({
        access_token: tokens.access_token,
        refresh_token: tokens.refresh_token,
      })
    ).catch(() => {});
  };

  const clearStoredAuthArtifacts = () => {
    clearPersistedUserState();
    clearTokens();
    if (typeof window === 'undefined') return;
    const clearMatchingKeys = (storage) => {
      try {
        const keysToRemove = [];
        for (let index = 0; index < storage.length; index += 1) {
          const key = storage.key(index);
          if (key && key.startsWith('sb-')) keysToRemove.push(key);
        }
        keysToRemove.forEach((key) => storage.removeItem(key));
      } catch {
        // Ignore storage failures.
      }
    };
    clearMatchingKeys(window.localStorage);
    clearMatchingKeys(window.sessionStorage);
  };

  const redirectToMainPage = () => {
    if (typeof window === 'undefined') return;
    window.location.replace('/');
  };

  const broadcastSignOut = (reason = 'manual') => {
    if (typeof window === 'undefined') return;
    const payload = JSON.stringify({ reason, at: Date.now() });
    try {
      window.localStorage.setItem(AUTH_SIGN_OUT_EVENT_KEY, payload);
    } catch {
      // Ignore storage failures and rely on the broadcast channel.
    }
    try {
      authBroadcastRef.current?.postMessage(payload);
    } catch {
      // Ignore broadcast failures and rely on storage events.
    }
  };

  const applyUserState = (currentUser) => {
    if (!currentUser) {
      setUser(null);
      setUserRole(null);
      setRequireInviteOnboarding(false);
      clearStoredAuthArtifacts();
      return;
    }
    const { role, requireInviteOnboarding: requiresOnboarding } = getAccountFlags(currentUser);
    setUser(currentUser);
    setUserRole(role || 'user');
    setRequireInviteOnboarding(requiresOnboarding);
    persistUserState(currentUser, role || 'user', requiresOnboarding);
  };

  const bumpAuthRefreshKey = () => setAuthRefreshKey((previousKey) => previousKey + 1);

  const clearUserState = ({ clearCache = true } = {}) => {
    setUser(null);
    setUserRole(null);
    setRequireInviteOnboarding(false);
    if (clearCache) clearPersistedUserState();
  };

  useEffect(() => {
    latestUserRef.current = user;
  }, [user]);

  // Returns a valid access token, refreshing via the auth-service when needed.
  // Never throws and never logs the user out — on failure it returns whatever
  // token we have (possibly stale) or '' so the caller can decide.
  const getAccessToken = async ({ forceRefresh = false } = {}) => {
    const tokens = tokensRef.current || readStoredTokens();
    if (!tokens) return '';

    const fresh = tokens.access_token
      && tokens.expires_at
      && tokens.expires_at - Date.now() > TOKEN_REFRESH_SKEW_MS;
    if (!forceRefresh && fresh) {
      return tokens.access_token;
    }

    // De-dupe: if a refresh is already running, await it instead of starting a
    // second one — a parallel refresh with the same (single-use) refresh token
    // rotates it out and makes the loser fail with "Invalid or expired token".
    if (!refreshInFlightRef.current) {
      const refreshToken = tokens.refresh_token;
      refreshInFlightRef.current = refreshSessionRequest(refreshToken)
        .then((refreshed) => storeTokens(refreshed)?.access_token || '')
        .finally(() => { refreshInFlightRef.current = null; });
    }

    try {
      const refreshedToken = await refreshInFlightRef.current;
      return refreshedToken || tokensRef.current?.access_token || tokens.access_token || '';
    } catch {
      return tokensRef.current?.access_token || tokens.access_token || '';
    }
  };

  // Kept for API compatibility with callers that expect a session-like object.
  const ensureActiveSession = async ({ forceRefresh = false } = {}) => {
    const accessToken = await getAccessToken({ forceRefresh });
    if (!accessToken) return null;
    const tokens = tokensRef.current;
    return {
      access_token: accessToken,
      refresh_token: tokens?.refresh_token || '',
      expires_at: tokens?.expires_at ? Math.floor(tokens.expires_at / 1000) : undefined,
    };
  };

  useEffect(() => {
    let isUnmounted = false;

    // Authenticated API requests can silently recover a stale token by asking
    // the auth-service for a fresh one. (No unauthorized handler: a 401 must
    // NEVER sign the user out — only manual sign-out or a block can.)
    setTokenRefresher(async () => {
      try {
        return await getAccessToken({ forceRefresh: true });
      } catch {
        return '';
      }
    });
    setUnauthorizedHandler(null);

    const forceSignOut = ({ redirectHome = false, reason = 'blocked' } = {}) => {
      clearUserState();
      clearStoredAuthArtifacts();
      bumpAuthRefreshKey();
      broadcastSignOut(reason);
      try {
        supabase?.auth.signOut();
      } catch {
        // Best-effort thin-client cleanup.
      }
      if (redirectHome) redirectToMainPage();
    };

    // Validate the stored session against the auth-service and hydrate the user.
    const bootstrap = async () => {
      let tokens = tokensRef.current || readStoredTokens();

      // No stored session yet — an invite/recovery link may have established one
      // in the URL. Adopt it into our token store so onboarding can proceed.
      if (!tokens && supabase) {
        try {
          const { data } = await supabase.auth.getSession();
          if (data?.session?.access_token && data?.session?.refresh_token) {
            tokens = storeTokens(data.session);
          }
        } catch {
          // No URL session; fall through.
        }
      }

      if (!tokens) {
        // No session at all (never signed in, signed out, or migrating from the
        // old client). Nothing to keep — clear any stale cached user. This is
        // not an auto-logout: there is genuinely no token to work with.
        if (!isUnmounted) clearUserState();
        return;
      }
      tokensRef.current = tokens;
      seedThinClient(tokens);

      try {
        const accessToken = await getAccessToken();
        if (!accessToken) return; // keep cached user; never auto-logout
        const profile = await fetchCurrentUser(accessToken);
        if (isUnmounted) return;
        if (getAccountFlags(profile).blocked) {
          forceSignOut({ redirectHome: true, reason: 'blocked' });
          return;
        }
        applyUserState(profile);
      } catch {
        // Validation failed (e.g. transient). Per the no-auto-logout rule we
        // keep the cached user rather than signing them out.
      }
    };

    bootstrap().finally(() => {
      if (!isUnmounted) setLoading(false);
    });

    // Poll for an admin block so a blocked user is signed out (allowed case).
    const blockedPollId = window.setInterval(async () => {
      if (!latestUserRef.current) return;
      try {
        const accessToken = await getAccessToken();
        if (!accessToken) return;
        const profile = await fetchCurrentUser(accessToken);
        if (getAccountFlags(profile).blocked) {
          forceSignOut({ redirectHome: true, reason: 'blocked' });
        }
      } catch {
        // Ignore — a failed check must not log anyone out.
      }
    }, BLOCKED_POLL_INTERVAL_MS);

    if (typeof window !== 'undefined' && typeof BroadcastChannel !== 'undefined') {
      authBroadcastRef.current = new BroadcastChannel(AUTH_BROADCAST_CHANNEL);
    }

    const handleSharedSignOut = () => {
      clearUserState();
      clearStoredAuthArtifacts();
      bumpAuthRefreshKey();
      redirectToMainPage();
    };

    const handleStorage = (event) => {
      if (event.key !== AUTH_SIGN_OUT_EVENT_KEY || !event.newValue) return;
      handleSharedSignOut();
    };
    const handleBroadcastMessage = () => handleSharedSignOut();

    window.addEventListener('storage', handleStorage);
    authBroadcastRef.current?.addEventListener('message', handleBroadcastMessage);

    return () => {
      isUnmounted = true;
      setUnauthorizedHandler(null);
      setTokenRefresher(null);
      window.clearInterval(blockedPollId);
      window.removeEventListener('storage', handleStorage);
      authBroadcastRef.current?.removeEventListener('message', handleBroadcastMessage);
      authBroadcastRef.current?.close?.();
      authBroadcastRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const signIn = async (email, password) => {
    const session = await loginWithPassword(email, password);
    const accessToken = session?.access_token || '';
    const refreshToken = session?.refresh_token || '';
    if (!accessToken || !refreshToken) {
      throw new Error('Login succeeded but no session tokens were returned.');
    }
    storeTokens(session);

    const profile = await fetchCurrentUser(accessToken);
    if (getAccountFlags(profile).blocked) {
      clearUserState();
      clearStoredAuthArtifacts();
      bumpAuthRefreshKey();
      broadcastSignOut('blocked');
      throw new Error('Your account is blocked. Please contact an administrator.');
    }

    applyUserState(profile);
    bumpAuthRefreshKey();
    return { user: profile };
  };

  const signUp = async ({ email, password, phoneNumber = '' }) => {
    if (!isPasswordStrong(password)) {
      throw new Error(PASSWORD_POLICY_MESSAGE);
    }
    const username = deriveUsernameFromEmail(email);
    const data = await signupRequest({
      email,
      password,
      username,
      phone_number: phoneNumber.trim(),
    });
    // Intentionally do NOT bump the auth refresh key here: signup does not log
    // the user in, and bumping it remounts the login page (keyed on it), which
    // would wipe the "account created — pending admin validation" screen.
    return data;
  };

  const updateProfile = async ({
    username,
    phoneNumber = '',
    profilePictureFile = null,
    removeProfilePicture = false,
    newPassword = '',
    completeInviteOnboarding = false,
  }) => {
    const accessToken = await getAccessToken();
    if (!accessToken) throw new Error('Your session has expired. Please sign in again.');

    const currentUser = latestUserRef.current;
    const existingMetadata = currentUser?.user_metadata || {};
    const resolvedUsername = (username || '').trim()
      || (existingMetadata.username || '').trim()
      || deriveUsernameFromEmail(currentUser?.email || '');
    if (!resolvedUsername) throw new Error('Username is required.');

    let uploadedProfilePictureUrl = removeProfilePicture
      ? ''
      : (existingMetadata.profile_picture || '').trim();

    if (profilePictureFile instanceof File) {
      if (!supabase) throw new Error('Storage is not configured.');
      const originalName = profilePictureFile.name || 'profile-image';
      const extension = originalName.includes('.') ? originalName.split('.').pop() : 'png';
      const safeExtension = (extension || 'png').replace(/[^a-zA-Z0-9]/g, '').toLowerCase() || 'png';
      const targetPath = `${currentUser?.id || 'user'}/${Date.now()}.${safeExtension}`;
      const { error: uploadError } = await supabase.storage
        .from(profileBucket)
        .upload(targetPath, profilePictureFile, { upsert: true });
      if (uploadError) {
        throw new Error(`Profile picture upload failed: ${uploadError.message}`);
      }
      const { data: publicData } = supabase.storage.from(profileBucket).getPublicUrl(targetPath);
      uploadedProfilePictureUrl = publicData?.publicUrl || uploadedProfilePictureUrl;
    }

    const payload = {
      username: resolvedUsername,
      phone_number: phoneNumber.trim(),
      profile_picture: uploadedProfilePictureUrl,
    };
    if (completeInviteOnboarding) payload.invite_onboarding_completed = true;
    if (newPassword && newPassword.trim()) {
      if (!isPasswordStrong(newPassword.trim())) {
        throw new Error(PASSWORD_POLICY_MESSAGE);
      }
      payload.new_password = newPassword.trim();
    }

    const updatedProfile = await updateProfileRequest(accessToken, payload);
    applyUserState(updatedProfile);
    if (completeInviteOnboarding) setRequireInviteOnboarding(false);
    return updatedProfile;
  };

  const updatePassword = async (newPassword) => {
    if (!isPasswordStrong(newPassword)) {
      throw new Error(PASSWORD_POLICY_MESSAGE);
    }
    const accessToken = await getAccessToken();
    if (!accessToken) throw new Error('Your session has expired. Please sign in again.');
    return updatePasswordRequest(accessToken, newPassword);
  };

  const signOut = async () => {
    const accessToken = tokensRef.current?.access_token || '';
    clearUserState();
    clearStoredAuthArtifacts();
    bumpAuthRefreshKey();
    broadcastSignOut('manual');
    try {
      if (accessToken) await logoutRequest(accessToken);
    } catch {
      // Best-effort server-side logout; local tokens are already cleared.
    }
    try {
      await supabase?.auth.signOut();
    } catch {
      // Best-effort thin-client cleanup.
    }
    redirectToMainPage();
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        userRole,
        requireInviteOnboarding,
        authRefreshKey,
        loading,
        signIn,
        signUp,
        signOut,
        updatePassword,
        updateProfile,
        getAccessToken,
        ensureActiveSession,
        supabase,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
}
