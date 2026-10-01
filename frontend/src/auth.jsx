import { createContext, useContext, useState } from "react";
import {
  api,
  clearSession,
  getStoredUser,
  getToken,
  storeSession,
} from "./api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(getToken() ? getStoredUser() : null);

  async function login(email, password) {
    const data = await api.login(email, password);
    storeSession(data.access_token, data.user);
    setUser(data.user);
    return data.user;
  }

  function logout() {
    clearSession();
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
