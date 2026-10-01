import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";

export default function UsersPage() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState([]);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    email: "",
    name: "",
    role: "operator",
    password: "",
  });

  async function load() {
    try {
      setUsers(await api.listUsers());
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function create(event) {
    event.preventDefault();
    setError("");
    try {
      await api.createUser(form);
      setForm({ email: "", name: "", role: "operator", password: "" });
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function patch(id, payload) {
    setError("");
    try {
      await api.updateUser(id, payload);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div>
      <h1>Users</h1>
      {error && <p className="error">{error}</p>}

      <form className="card" onSubmit={create}>
        <strong>Create user</strong>
        <div className="row">
          <div>
            <label>Email</label>
            <input
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              required
            />
          </div>
          <div>
            <label>Name</label>
            <input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              required
            />
          </div>
          <div>
            <label>Role</label>
            <select
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value })}
            >
              <option value="client">client</option>
              <option value="operator">operator</option>
              <option value="admin">admin</option>
            </select>
          </div>
          <div>
            <label>Password (min 8 chars)</label>
            <input
              type="password"
              minLength={8}
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              required
            />
          </div>
          <div style={{ flex: 0 }}>
            <button type="submit">Create</button>
          </div>
        </div>
      </form>

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Email</th>
              <th>Name</th>
              <th>Role</th>
              <th>Active</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.id}</td>
                <td>{u.email}</td>
                <td>{u.name}</td>
                <td>
                  <select
                    value={u.role}
                    disabled={u.id === me.id}
                    onChange={(e) => patch(u.id, { role: e.target.value })}
                  >
                    <option value="client">client</option>
                    <option value="operator">operator</option>
                    <option value="admin">admin</option>
                  </select>
                </td>
                <td>{u.is_active ? "yes" : "no"}</td>
                <td>
                  {u.id !== me.id &&
                    (u.is_active ? (
                      <button
                        className="danger"
                        onClick={() => patch(u.id, { is_active: false })}
                      >
                        deactivate
                      </button>
                    ) : (
                      <button
                        className="secondary"
                        onClick={() => patch(u.id, { is_active: true })}
                      >
                        reactivate
                      </button>
                    ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
