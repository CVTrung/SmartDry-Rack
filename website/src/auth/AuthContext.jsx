import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';

import {
  loginWithDeviceId,
  logoutFromFirebase,
  observeAuthState,
} from '../services/authService.js';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => observeAuthState((account) => {
    setUser(account);
    setLoading(false);
  }), []);

  const value = useMemo(() => ({
    user,
    loading,
    async login(deviceId, password) {
      const account = await loginWithDeviceId(deviceId, password);
      setUser(account);
    },
    async logout() {
      await logoutFromFirebase();
      setUser(null);
    },
  }), [loading, user]);

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error('useAuth phải được dùng bên trong AuthProvider.');
  }

  return context;
}
