import { useState, useCallback } from 'react';
import { auth } from '../api/client';

export function useAuth() {
  const [isAdmin, setIsAdmin] = useState(false);

  const login = useCallback(async (password: string) => {
    await auth.login(password);
    setIsAdmin(true);
  }, []);

  const logout = useCallback(async () => {
    try {
      await auth.logout();
    } catch {
      // ignore
    }
    setIsAdmin(false);
  }, []);

  return { isAdmin, setIsAdmin, login, logout };
}
