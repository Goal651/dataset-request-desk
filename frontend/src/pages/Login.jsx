import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(email, password);
      navigate("/");
    } catch (err) {
      setError(err.message || "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <div className="card">
        <h1>Dataset Request Desk</h1>
        <form onSubmit={submit}>
          <label>Email</label>
          <input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            type="email"
            required
          />
          <label>Password</label>
          <input
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            type="password"
            required
          />
          {error && <p className="error">{error}</p>}
          <div className="actions">
            <button type="submit" disabled={busy}>
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </div>
        </form>
      </div>
      <p className="muted">
        Seed accounts: admin@example.com / admin123 · ops1@example.com / ops123
        · client-a@example.com / client123
      </p>
    </div>
  );
}
