import { createContext, useContext, useState, useEffect, useRef } from 'react';
import { createClient } from '@supabase/supabase-js';
import { isPasswordStrong, PASSWORD_POLICY_MESSAGE } from '../utils/passwordPolicy';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;
const profileBucket = import.meta.env.VITE_SUPABASE_PROFILE_BUCKET || 'profiles';

const supabase =
  supabaseUrl && supabaseAnonKey
    ? createClient(supabaseUrl, supabaseAnonKey)
    : null;

const AuthContext = createContext(null);
const AUTH_OPERATION_TIMEOUT_MS = 8000;

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
  const [user, setUser] = useState(null);
  const [userRole, setUserRole] = useState(null);
  const [requireInviteOnboarding, setRequireInviteOnboarding] = useState(false);
  const [authRefreshKey, setAuthRefreshKey] = useState(0);
  const [loading, setLoading] = useState(true);
  const authMutationInFlightRef = useRef(false);
  const latestUserRef = useRef(null);
  const manualSignOutRef = useRef(false);

  const applyUserState = (currentUser) => {
    if (!currentUser) {
      setUser(null);
      setUserRole(null);
      setRequireInviteOnboarding(false);
      return;
    }

    const { role, requireInviteOnboarding: requiresOnboarding } = getAccountFlags(currentUser);
    setUser(currentUser);
    setUserRole(role || 'user');
    setRequireInviteOnboarding(requiresOnboarding);
  };

  const bumpAuthRefreshKey = () => {
    setAuthRefreshKey((previousKey) => previousKey + 1);
  };

  useEffect(() => {
    latestUserRef.current = user;
  }, [user]);

  const clearUserState = () => {
    setUser(null);
    setUserRole(null);
    setRequireInviteOnboarding(false);
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

    if (session?.user) {
      applyUserState(session.user);
    }

    return session;
  };

  useEffect(() => {
    if (!supabase) {
      setLoading(false);
      return;
    }
    let isUnmounted = false;
    let isEnforcing = false;
    let hasQueuedEnforcement = false;
    let queuedSessionUser = null;
    let isSigningOut = false;

    const forceSignOut = async ({ redirectHome = false } = {}) => {
      if (isSigningOut) return;
      isSigningOut = true;
      try {
        await supabase.auth.signOut();
        clearUserState();
        if (redirectHome) {
          window.location.replace('/');
        }
      } finally {
        isSigningOut = false;
      }
    };

    const enforceAccountState = async (sessionUser = undefined) => {
      if (authMutationInFlightRef.current) return;
      if (isEnforcing) {
        hasQueuedEnforcement = true;
        queuedSessionUser = sessionUser ?? null;
        return;
      }
      isEnforcing = true;

      let currentUser = sessionUser;
      try {
        if (currentUser === undefined) {
          try {
            const session = await ensureActiveSession();
            currentUser = session?.user ?? null;
          } catch {
            currentUser = latestUserRef.current;
          }
        } else if (currentUser) {
          // Refresh with latest server-side metadata when we already have a session user.
          try {
            const { data, error } = await withTimeout(supabase.auth.getUser());
            if (!error && data?.user) {
              currentUser = data.user;
            }
          } catch {
            // Keep session user if live fetch fails.
          }
        }

        if (!currentUser) {
          if (!manualSignOutRef.current && latestUserRef.current) {
            if (!isUnmounted) {
              applyUserState(latestUserRef.current);
            }
            return;
          }
          if (!isUnmounted && manualSignOutRef.current) {
            clearUserState();
          }
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
      } finally {
        isEnforcing = false;
        if (hasQueuedEnforcement) {
          const nextSessionUser = queuedSessionUser;
          hasQueuedEnforcement = false;
          queuedSessionUser = null;
          void enforceAccountState(nextSessionUser);
        }
      }
    };

    Promise.resolve()
      .then(() => ensureActiveSession().catch(() => null))
      .then(() => enforceAccountState(undefined))
      .catch(() => {
        if (!isUnmounted) {
          setLoading(false);
        }
      })
      .finally(() => {
        if (!isUnmounted) {
          setLoading(false);
        }
      });

    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      async (event, session) => {
        if (event === 'SIGNED_OUT') {
          if (!manualSignOutRef.current) {
            try {
              const recoveredSession = await ensureActiveSession({ forceRefresh: true });
              if (recoveredSession?.user) {
                await enforceAccountState(recoveredSession.user);
                return;
              }
            } catch {
              if (latestUserRef.current) {
                applyUserState(latestUserRef.current);
                return;
              }
            }
          }
          clearUserState();
          return;
        }
        if (!session?.user) {
          await enforceAccountState(undefined);
          return;
        }
        await enforceAccountState(session.user);
      }
    );

    const verifySessionAccountState = async ({ forceRefresh = false } = {}) => {
      try {
        await ensureActiveSession({ forceRefresh });
      } catch {
        // Fall back to direct account enforcement below.
      }
      await enforceAccountState(undefined);
    };

    const intervalId = window.setInterval(() => {
      void verifySessionAccountState();
    }, 15000);

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        void verifySessionAccountState({ forceRefresh: true });
      }
    };

    const handleWindowFocus = () => {
      void verifySessionAccountState({ forceRefresh: true });
    };

    const handleOnline = () => {
      void verifySessionAccountState({ forceRefresh: true });
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('focus', handleWindowFocus);
    window.addEventListener('online', handleOnline);

    return () => {
      isUnmounted = true;
      subscription.unsubscribe();
      window.clearInterval(intervalId);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('focus', handleWindowFocus);
      window.removeEventListener('online', handleOnline);
    };
  }, []);

  const signIn = async (email, password) => {
    if (!supabase) throw new Error('Supabase not configured');
    const { data, error } = await supabase.auth.signInWithPassword({
      email,
      password,
    });
    if (error) {
      const rawMessage = (error.message || '').toLowerCase();
      if (rawMessage.includes('email not confirmed') || rawMessage.includes('email_not_confirmed')) {
        throw new Error('Your account is validated but your email is not confirmed. Please check your inbox and validate your email first.');
      }
      throw error;
    }

    const { blocked } = getAccountFlags(data?.user);
    if (blocked) {
      await supabase.auth.signOut();
      throw new Error('Your account is blocked. Please contact an administrator.');
    }

    applyUserState(data?.user ?? null);
    bumpAuthRefreshKey();
    return data;
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
      const { data: currentData } = await supabase.auth.getUser();
      const currentUser = currentData?.user;
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
      setUser(data?.user ?? currentUser ?? null);
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
      const { error } = await supabase.auth.signOut();
      if (error) throw error;
      clearUserState();
      bumpAuthRefreshKey();
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
