import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";

const STATUSES = [
  "",
  "submitted",
  "in_progress",
  "delivered",
  "accepted",
  "rejected",
];

export default function RequestsPage() {
  const { user } = useAuth();
  const isClient = user.role === "client";
  const [rows, setRows] = useState([]);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  // create form (clients only)
  const [taskName, setTaskName] = useState("");
  const [count, setCount] = useState(10);
  const [deadline, setDeadline] = useState("");
  const [notes, setNotes] = useState("");

  async function load() {
    try {
      setRows(await api.listRequests(status || undefined));
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  async function create(event) {
    event.preventDefault();
    setError("");
    try {
      await api.createRequest({
        task_name: taskName,
        episodes_requested: Number(count),
        deadline,
        notes: notes || null,
      });
      setTaskName("");
      setNotes("");
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div>
      <h1>Requests</h1>
      {error && <p className="error">{error}</p>}

      {isClient && (
        <form className="card" onSubmit={create}>
          <strong>New request</strong>
          <div className="row">
            <div>
              <label>Task name</label>
              <input
                value={taskName}
                onChange={(e) => setTaskName(e.target.value)}
                required
              />
            </div>
            <div>
              <label>Episodes requested</label>
              <input
                type="number"
                min="1"
                value={count}
                onChange={(e) => setCount(e.target.value)}
                required
              />
            </div>
            <div>
              <label>Deadline</label>
              <input
                type="date"
                value={deadline}
                onChange={(e) => setDeadline(e.target.value)}
                required
              />
            </div>
            <div>
              <label>Notes</label>
              <input value={notes} onChange={(e) => setNotes(e.target.value)} />
            </div>
            <div style={{ flex: 0 }}>
              <button type="submit">Create</button>
            </div>
          </div>
        </form>
      )}

      <div className="card">
        <div className="row" style={{ marginBottom: 10 }}>
          <div>
            <label>Filter by status</label>
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s || "all statuses"}
                </option>
              ))}
            </select>
          </div>
        </div>
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Task</th>
              <th>Client</th>
              <th>Assigned</th>
              <th>Deadline</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{r.id}</td>
                <td>{r.task_name}</td>
                <td>{r.client_name}</td>
                <td>
                  {r.assigned_count} / {r.episodes_requested}
                </td>
                <td>{r.deadline}</td>
                <td>
                  <span className={`badge ${r.status}`}>{r.status}</span>
                </td>
                <td>
                  <Link to={`/requests/${r.id}`}>open</Link>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan="7" className="muted">
                  No requests yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
