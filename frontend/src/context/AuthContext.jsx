import { createContext, useContext, useState, useEffect, useRef } from 'react';
import { createClient } from '@supabase/supabase-js';
import { isPasswordStrong, PASSWORD_POLICY_MESSAGE } from '../utils/passwordPolicy';
import { loginWithPassword, setUnauthorizedHandler, setTokenRefresher } from '../config/api';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;
const profileBucket = import.meta.env.VITE_SUPABASE_PROFILE_BUCKET || 'profiles';

const supabase =
  supabaseUrl && supabaseAnonKey
    ? createClient(supabaseUrl, supabaseAnonKey)
    : null;

const AuthContext = createContext(null);
const AUTH_OPERATION_TIMEOUT_MS = 8000;
const AUTH_CACHE_KEY = 'agent.auth.cache.v1';
const AUTH_SIGN_OUT_EVENT_KEY = 'agent.auth.signout.v1';
const AUTH_BROADCAST_CHANNEL = 'agent-auth';

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
  return {
    role,
    blocked,
    validated,
    username,
    requireInviteOnboarding,
  };
}

export function AuthProvider({ children }) {
  const readCachedAuthState = () => {
    if (typeof window === 'undefined') {
      return {
        user: null,
        userRole: null,
        requireInviteOnboarding: false,
      };
    }

    try {
      const rawValue = window.localStorage.getItem(AUTH_CACHE_KEY);
      if (!rawValue) {
        return {
          user: null,
          userRole: null,
          requireInviteOnboarding: false,
        };
      }

      const parsed = JSON.parse(rawValue);
      const cachedUser = parsed?.user ?? null;
      return {
        user: cachedUser,
        userRole: parsed?.userRole || cachedUser?.user_metadata?.role || null,
        requireInviteOnboarding: parsed?.requireInviteOnboarding === true,
      };
    } catch {
      return {
        user: null,
        userRole: null,
        requireInviteOnboarding: false,
      };
    }
  };

  const cachedAuthState = readCachedAuthState();
  const [user, setUser] = useState(cachedAuthState.user);
  const [userRole, setUserRole] = useState(cachedAuthState.userRole);
  const [requireInviteOnboarding, setRequireInviteOnboarding] = useState(cachedAuthState.requireInviteOnboarding);
  const [authRefreshKey, setAuthRefreshKey] = useState(0);
  const [loading, setLoading] = useState(!cachedAuthState.user);
  const authMutationInFlightRef = useRef(false);
  const latestUserRef = useRef(cachedAuthState.user);
  const manualSignOutRef = useRef(false);
  const authBroadcastRef = useRef(null);

  const persistUserState = (currentUser, role, requiresOnboarding) => {
    if (typeof window === 'undefined') return;
    try {
      window.localStorage.setItem(
        AUTH_CACHE_KEY,
        JSON.stringify({
          user: currentUser,
          userRole: role,
          requireInviteOnboarding: requiresOnboarding,
        })
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
      // Ignore storage failures and keep in-memory auth state.
    }
  };

  const clearStoredAuthArtifacts = () => {
    clearPersistedUserState();
    if (typeof window === 'undefined') return;

    const clearMatchingKeys = (storage) => {
      try {
        const keysToRemove = [];
        for (let index = 0; index < storage.length; index += 1) {
          const key = storage.key(index);
          if (key && key.startsWith('sb-')) {
            keysToRemove.push(key);
          }
        }
        keysToRemove.forEach((key) => storage.removeItem(key));
      } catch {
        // Ignore storage failures and keep in-memory auth state.
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

    const payload = JSON.stringify({
      reason,
      at: Date.now(),
    });

    try {
      window.localStorage.setItem(AUTH_SIGN_OUT_EVENT_KEY, payload);
    } catch {
      // Ignore storage failures and rely on local cleanup.
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

  const bumpAuthRefreshKey = () => {
    setAuthRefreshKey((previousKey) => previousKey + 1);
  };

  useEffect(() => {
    latestUserRef.current = user;
  }, [user]);

  const clearUserState = ({ clearCache = true } = {}) => {
    setUser(null);
    setUserRole(null);
    setRequireInviteOnboarding(false);
    if (clearCache) {
      clearPersistedUserState();
    }
  };

  const withTimeout = async (promise, timeoutMs = AUTH_OPERATION_TIMEOUT_MS) => {
    let timeoutId;
    try {
      return await Promise.race([
        promise,
        new Promise((_, reject) => {
          timeoutId = window.setTimeout(() => {
            reject(new Error('Authentication request timed out.'));
          }, timeoutMs);
        }),
      ]);
    } finally {
      if (timeoutId) {
        window.clearTimeout(timeoutId);
      }
    }
  };

  const hasUsableAccessToken = (session) => (
    Boolean(
      session?.access_token
      && (!session?.expires_at || (session.expires_at * 1000) > (Date.now() + 15_000))
    )
  );

  const ensureActiveSession = async ({ forceRefresh = false } = {}) => {
    if (!supabase) return null;

    const { data, error } = await withTimeout(supabase.auth.getSession());
    if (error) {
      throw error;
    }

    let session = data?.session ?? null;
    const expiresSoon = session?.expires_at
      ? (session.expires_at * 1000) - Date.now() < 60_000
      : false;

    if ((forceRefresh || expiresSoon) && session?.refresh_token) {
      try {
        const { data: refreshedData, error: refreshError } = await withTimeout(
          supabase.auth.refreshSession()
        );
        if (refreshError) {
          throw refreshError;
        }
        session = refreshedData?.session ?? session;
      } catch (refreshError) {
        if (!hasUsableAccessToken(session)) {
          throw refreshError;
        }
      }
    }

    return session;
  };

  useEffect(() => {
    if (!supabase) {
      setLoading(false);
      return;
    }
    let isUnmounted = false;
    let isSigningOut = false;

    const forceSignOut = async ({ redirectHome = false, reason = 'blocked' } = {}) => {
      if (isSigningOut) return;
      isSigningOut = true;
      try {
        clearUserState();
        bumpAuthRefreshKey();
        broadcastSignOut(reason);
        await supabase.auth.signOut();
        if (redirectHome) {
          redirectToMainPage();
        }
      } finally {
        isSigningOut = false;
      }
    };

    // Let the API layer silently recover a stale token: force-refresh the
    // Supabase session and hand back a fresh access token so the failed request
    // can be retried without the user noticing.
    setTokenRefresher(async () => {
      try {
        return await getAccessToken({ forceRefresh: true });
      } catch {
        return '';
      }
    });

    // Only reached when the refresh above could not save the session: tear it
    // down and send the user back to the login page.
    setUnauthorizedHandler(() => {
      forceSignOut({ redirectHome: true, reason: 'expired' });
    });

    const syncKnownUser = async (currentUser) => {
      if (!currentUser) {
        return;
      }

      const { blocked } = getAccountFlags(currentUser);
      if (blocked) {
        await forceSignOut({ redirectHome: true });
        return;
      }

      if (!isUnmounted) {
        applyUserState(currentUser);
      }
    };

    Promise.resolve()
      .then(() => ensureActiveSession().catch(() => null))
      .then(async (session) => {
        if (session?.user) {
          await syncKnownUser(session.user);
          return;
        }

        if (!latestUserRef.current && !isUnmounted) {
          clearUserState();
        }
      })
      .catch(() => {
        if (!isUnmounted && !latestUserRef.current) {
          setLoading(false);
        }
      })
      .finally(() => {
        if (!isUnmounted) {
          setLoading(false);
        }
      });

    if (typeof window !== 'undefined' && typeof BroadcastChannel !== 'undefined') {
      authBroadcastRef.current = new BroadcastChannel(AUTH_BROADCAST_CHANNEL);
    }

    const handleSharedSignOut = () => {
      clearUserState();
      bumpAuthRefreshKey();
      redirectToMainPage();
    };

    const handleStorage = (event) => {
      if (event.key !== AUTH_SIGN_OUT_EVENT_KEY || !event.newValue) {
        return;
      }
      handleSharedSignOut();
    };

    const handleBroadcastMessage = () => {
      handleSharedSignOut();
    };

    window.addEventListener('storage', handleStorage);
    authBroadcastRef.current?.addEventListener('message', handleBroadcastMessage);

    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      async (event, session) => {
        if (event === 'SIGNED_OUT') {
          if (manualSignOutRef.current) {
            clearUserState();
          }
          return;
        }

        if (!session?.user) {
          return;
        }

        await syncKnownUser(session.user);
      }
    );

    return () => {
      isUnmounted = true;
      setUnauthorizedHandler(null);
      setTokenRefresher(null);
      subscription.unsubscribe();
      window.removeEventListener('storage', handleStorage);
      authBroadcastRef.current?.removeEventListener('message', handleBroadcastMessage);
      authBroadcastRef.current?.close?.();
      authBroadcastRef.current = null;
    };
  }, []);

  const signIn = async (email, password) => {
    if (!supabase) throw new Error('Supabase not configured');
    const data = await loginWithPassword(email, password);

    const accessToken = data?.access_token || '';
    const refreshToken = data?.refresh_token || '';
    if (!accessToken || !refreshToken) {
      throw new Error('Login succeeded but no session tokens were returned.');
    }

    const { data: sessionData, error } = await supabase.auth.setSession({
      access_token: accessToken,
      refresh_token: refreshToken,
    });
    if (error) throw error;

    const resolvedUser = sessionData?.user ?? null;
    const { blocked } = getAccountFlags(resolvedUser);
    if (blocked) {
      clearUserState();
      bumpAuthRefreshKey();
      broadcastSignOut('blocked');
      await supabase.auth.signOut();
      throw new Error('Your account is blocked. Please contact an administrator.');
    }

    applyUserState(resolvedUser);
    bumpAuthRefreshKey();
    return sessionData;
  };

  const signUp = async ({ email, password, phoneNumber = '' }) => {
    if (!supabase) throw new Error('Supabase not configured');
    if (!isPasswordStrong(password)) {
      throw new Error(PASSWORD_POLICY_MESSAGE);
    }
    const username = deriveUsernameFromEmail(email);
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: {
          role: 'user',
          username,
          phone_number: phoneNumber.trim(),
          profile_picture: '',
          invite_onboarding_completed: true,
        },
      },
    });
    if (error) throw error;
    bumpAuthRefreshKey();
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
    if (!supabase) throw new Error('Supabase not configured');
    authMutationInFlightRef.current = true;
    try {
      const currentUser = latestUserRef.current;
      const existingMetadata = currentUser?.user_metadata || {};
      const resolvedUsername = (username || '').trim()
        || (existingMetadata.username || '').trim()
        || deriveUsernameFromEmail(currentUser?.email || '');

      if (!resolvedUsername) {
        throw new Error('Username is required.');
      }
      let uploadedProfilePictureUrl = removeProfilePicture
        ? ''
        : (existingMetadata.profile_picture || '').trim();

      if (profilePictureFile instanceof File) {
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

      const attributes = {
        data: {
          ...existingMetadata,
          username: resolvedUsername,
          phone_number: phoneNumber.trim(),
          profile_picture: uploadedProfilePictureUrl,
          ...(completeInviteOnboarding ? { invite_onboarding_completed: true } : {}),
        },
      };
      if (newPassword && newPassword.trim()) {
        if (!isPasswordStrong(newPassword.trim())) {
          throw new Error(PASSWORD_POLICY_MESSAGE);
        }
        attributes.password = newPassword.trim();
      }

      const { data, error } = await supabase.auth.updateUser(attributes);
      if (error) throw error;
      applyUserState(data?.user ?? currentUser ?? null);
      if (completeInviteOnboarding) {
        setRequireInviteOnboarding(false);
      }
      return data;
    } finally {
      authMutationInFlightRef.current = false;
    }
  };

  const updatePassword = async (newPassword) => {
    if (!supabase) throw new Error('Supabase not configured');
    if (!isPasswordStrong(newPassword)) {
      throw new Error(PASSWORD_POLICY_MESSAGE);
    }
    const { data, error } = await supabase.auth.updateUser({
      password: newPassword,
    });
    if (error) throw error;
    return data;
  };

  const getAccessToken = async ({ forceRefresh = false } = {}) => {
    if (!supabase) return '';
    try {
      const { data, error } = await withTimeout(supabase.auth.getSession());
      if (error) {
        throw error;
      }

      const currentSession = data?.session ?? null;
      if (!forceRefresh && currentSession?.access_token) {
        return currentSession.access_token;
      }

      const refreshedSession = await ensureActiveSession({ forceRefresh });
      return refreshedSession?.access_token || currentSession?.access_token || '';
    } catch {
      return '';
    }
  };

  const signOut = async () => {
    if (!supabase) return;
    manualSignOutRef.current = true;
    try {
      clearUserState();
      bumpAuthRefreshKey();
      broadcastSignOut('manual');
      const { error } = await supabase.auth.signOut();
      if (error) throw error;
      redirectToMainPage();
    } finally {
      manualSignOutRef.current = false;
    }
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
