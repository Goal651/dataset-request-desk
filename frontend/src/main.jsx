import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import LoginPage from "./pages/Login";
import RequestsPage from "./pages/Requests";
import RequestDetailPage from "./pages/RequestDetail";
import EpisodesPage from "./pages/Episodes";
import UsersPage from "./pages/Users";
import AnalyticsPage from "./pages/Analytics";
import Layout from "./components/Layout";
import "./styles.css";

function Protected({ children }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/"
            element={
              <Protected>
                <Layout />
              </Protected>
            }
          >
            <Route index element={<RequestsPage />} />
            <Route path="requests/:id" element={<RequestDetailPage />} />
            <Route path="episodes" element={<EpisodesPage />} />
            <Route path="users" element={<UsersPage />} />
            <Route path="analytics" element={<AnalyticsPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
