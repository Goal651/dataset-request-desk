import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";

function nextActions(status, role) {
  const staff = role === "operator" || role === "admin";
  const map = {
    submitted: staff ? [{ to: "in_progress", label: "Start work" }] : [],
    in_progress: staff ? [{ to: "delivered", label: "Deliver" }] : [],
    delivered:
      role === "client"
        ? [
            { to: "accepted", label: "Accept" },
            { to: "rejected", label: "Reject" },
          ]
        : [],
    rejected: staff ? [{ to: "in_progress", label: "Rework" }] : [],
    accepted: [],
  };
  return map[status] || [];
}

export default function RequestDetailPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const isStaff = user.role === "operator" || user.role === "admin";
  const [request, setRequest] = useState(null);
  const [exports, setExports] = useState([]);
  const [episodes, setEpisodes] = useState([]);
  const [filters, setFilters] = useState({
    task_name: "",
    quality: "",
    unassigned_only: true,
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api.getRequest(id);
      setRequest(data);
      if (
        isStaff &&
        ["submitted", "in_progress", "rejected"].includes(data.status)
      ) {
        setExports([]);
      } else {
        setExports(await api.listExports(id));
      }
    } catch (err) {
      setError(err.message);
    }
  }, [id, isStaff]);

  useEffect(() => {
    load();
  }, [load]);

  async function loadEpisodes() {
    try {
      const params = {};
      if (filters.task_name) params.task_name = filters.task_name;
      if (filters.quality) params.quality = filters.quality;
      if (filters.unassigned_only) params.unassigned_only = "true";
      setEpisodes(await api.listEpisodes({ ...params, limit: 50 }));
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    if (isStaff) loadEpisodes();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters, isStaff]);

  async function transition(to) {
    setBusy(true);
    setError("");
    try {
      await api.transition(id, to);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function assign(episodePk) {
    setBusy(true);
    setError("");
    try {
      await api.assign(id, episodePk);
      await Promise.all([load(), loadEpisodes()]);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function unassign(assignmentId) {
    setBusy(true);
    try {
      await api.unassign(id, assignmentId);
      await Promise.all([load(), loadEpisodes()]);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function retry(jobId) {
    setBusy(true);
    try {
      await api.retryExport(id, jobId);
      setTimeout(load, 3500); // give the worker a moment, then refresh
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (!request) return <p className="muted">{error || "Loading…"}</p>;

  const assignable = ["submitted", "in_progress", "rejected"].includes(
    request.status,
  );

  return (
    <div>
      <h1>
        Request #{request.id} — {request.task_name}{" "}
        <span className={`badge ${request.status}`}>{request.status}</span>
      </h1>
      {error && <p className="error">{error}</p>}

      <div className="card kv">
        <span>Client</span>
        <span>{request.client_name}</span>
        <span>Episodes</span>
        <span>
          {request.assigned_count} / {request.episodes_requested}
        </span>
        <span>Deadline</span>
        <span>{request.deadline}</span>
        <span>Notes</span>
        <span>{request.notes || "—"}</span>
      </div>

      {nextActions(request.status, user.role).length > 0 && (
        <div className="card">
          <strong>Actions</strong>
          <div className="actions">
            {nextActions(request.status, user.role).map((action) => (
              <button
                key={action.to}
                disabled={busy}
                onClick={() => transition(action.to)}
              >
                {action.label}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="card">
        <strong>Assigned episodes ({request.assigned_count})</strong>
        <table>
          <thead>
            <tr>
              <th>Episode</th>
              <th>Robot</th>
              <th>Quality</th>
              {isStaff && <th></th>}
            </tr>
          </thead>
          <tbody>
            {request.episodes.map((ep) => (
              <tr key={ep.id}>
                <td>
                  {ep.episode_id}{" "}
                  <span className="muted">({ep.task_name})</span>
                </td>
                <td>{ep.robot_id}</td>
                <td>
                  <span className={`badge ${ep.quality}`}>{ep.quality}</span>
                </td>
                {isStaff && assignable && (
                  <td>
                    <button
                      className="secondary"
                      disabled={busy}
                      onClick={() => unassign(ep.id)}
                    >
                      unassign
                    </button>
                  </td>
                )}
              </tr>
            ))}
            {request.episodes.length === 0 && (
              <tr>
                <td colSpan="4" className="muted">
                  Nothing assigned yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {exports.length > 0 && (
        <div className="card">
          <strong>Export jobs (background stretch)</strong>
          <table>
            <thead>
              <tr>
                <th>Episode</th>
                <th>Status</th>
                <th>Attempt</th>
                <th>Error</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {exports.map((job) => (
                <tr key={job.id}>
                  <td>{job.episode_ref}</td>
                  <td>
                    <span className={`badge ${job.status}`}>{job.status}</span>
                  </td>
                  <td>{job.attempt}</td>
                  <td className="muted">{job.error || "—"}</td>
                  <td>
                    {isStaff && job.status === "failed" && (
                      <button
                        className="secondary"
                        disabled={busy}
                        onClick={() => retry(job.id)}
                      >
                        retry
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {isStaff && assignable && (
        <div className="card">
          <strong>Find episodes to assign</strong>
          <div className="row">
            <div>
              <label>Task name contains</label>
              <input
                value={filters.task_name}
                onChange={(e) =>
                  setFilters({ ...filters, task_name: e.target.value })
                }
                placeholder="pick cup"
              />
            </div>
            <div>
              <label>Quality</label>
              <select
                value={filters.quality}
                onChange={(e) =>
                  setFilters({ ...filters, quality: e.target.value })
                }
              >
                <option value="">any</option>
                <option value="good">good</option>
                <option value="usable">usable</option>
              </select>
            </div>
          </div>
          <table>
            <thead>
              <tr>
                <th>Episode</th>
                <th>Task</th>
                <th>Robot</th>
                <th>Quality</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {episodes.map((ep) => (
                <tr key={ep.id}>
                  <td>{ep.episode_id}</td>
                  <td>{ep.task_name}</td>
                  <td>{ep.robot_id}</td>
                  <td>
                    <span className={`badge ${ep.quality}`}>{ep.quality}</span>
                  </td>
                  <td>
                    <button disabled={busy} onClick={() => assign(ep.id)}>
                      assign
                    </button>
                  </td>
                </tr>
              ))}
              {episodes.length === 0 && (
                <tr>
                  <td colSpan="5" className="muted">
                    No matching unassigned episodes.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      <div className="card">
        <strong>Status history</strong>
        <table>
          <thead>
            <tr>
              <th>When</th>
              <th>From → To</th>
              <th>By</th>
              <th>Note</th>
            </tr>
          </thead>
          <tbody>
            {request.events.map((event) => (
              <tr key={event.id}>
                <td>{new Date(event.created_at).toLocaleString()}</td>
                <td>
                  {event.from_status ?? "—"} →{" "}
                  <strong>{event.to_status}</strong>
                </td>
                <td>{event.actor_name}</td>
                <td className="muted">{event.note || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
