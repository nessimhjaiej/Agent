import { createContext, useContext, useState, useEffect } from 'react';
import { createClient } from '@supabase/supabase-js';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

const supabase =
  supabaseUrl && supabaseAnonKey
    ? createClient(supabaseUrl, supabaseAnonKey)
    : null;

const AuthContext = createContext(null);

function getAccountFlags(currentUser) {
  const role = currentUser?.user_metadata?.role || 'user';
  const appMetadata = currentUser?.app_metadata || {};
  const blocked = appMetadata.account_blocked === true;
  const validated = role === 'admin' || appMetadata.account_validated === true;
  return { role, blocked, validated };
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [userRole, setUserRole] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!supabase) {
      setLoading(false);
      return;
    }

    const forceSignOut = async ({ redirectHome = false } = {}) => {
      await supabase.auth.signOut();
      setUser(null);
      setUserRole(null);
      if (redirectHome) {
        window.location.replace('/');
      }
    };

    const enforceAccountState = async (sessionUser) => {
      const hasExplicitSessionUser = sessionUser !== undefined;
      const currentUser = hasExplicitSessionUser
        ? sessionUser
        : (await supabase.auth.getUser()).data?.user ?? null;
      if (!currentUser) {
        setUser(null);
        setUserRole(null);
        return;
      }

      const { blocked, validated, role } = getAccountFlags(currentUser);
      if (blocked || (!validated && role !== 'admin')) {
        await forceSignOut({ redirectHome: true });
        return;
      }

      setUser(currentUser);
      setUserRole(role || 'user');
    };

    supabase.auth.getSession().then(async ({ data: { session } }) => {
      await enforceAccountState(session?.user ?? null);
      setLoading(false);
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      async (_event, session) => {
        await enforceAccountState(session?.user ?? null);
      }
    );

    const verifySessionAccountState = async () => {
      const { data: { session } } = await supabase.auth.getSession();
      await enforceAccountState(session?.user ?? null);
    };

    const intervalId = window.setInterval(() => {
      verifySessionAccountState();
    }, 15000);

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        verifySessionAccountState();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      subscription.unsubscribe();
      window.clearInterval(intervalId);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, []);

  const signIn = async (email, password) => {
    if (!supabase) throw new Error('Supabase not configured');
    const { data, error } = await supabase.auth.signInWithPassword({
      email,
      password,
    });
    if (error) throw error;

    const { blocked, validated } = getAccountFlags(data?.user);
    if (blocked) {
      await supabase.auth.signOut();
      throw new Error('Your account is blocked. Please contact an administrator.');
    }
    if (!validated) {
      await supabase.auth.signOut();
      throw new Error('Your account is pending admin validation.');
    }

    return data;
  };

  const signUp = async (email, password) => {
    if (!supabase) throw new Error('Supabase not configured');
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: {
          role: 'user',
        },
      },
    });
    if (error) throw error;
    return data;
  };

  const updatePassword = async (newPassword) => {
    if (!supabase) throw new Error('Supabase not configured');
    const { data, error } = await supabase.auth.updateUser({
      password: newPassword,
    });
    if (error) throw error;
    return data;
  };

  const getAccessToken = async () => {
    if (!supabase) return '';
    const { data } = await supabase.auth.getSession();
    return data?.session?.access_token || '';
  };

  const signOut = async () => {
    if (!supabase) return;
    const { error } = await supabase.auth.signOut();
    if (error) throw error;
    setUser(null);
    setUserRole(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        userRole,
        loading,
        signIn,
        signUp,
        signOut,
        updatePassword,
        getAccessToken,
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
