import { useEffect, useState } from "react";
import { api } from "../api";

export default function EpisodesPage() {
  const [rows, setRows] = useState([]);
  const [filters, setFilters] = useState({
    task_name: "",
    quality: "",
    robot_id: "",
  });
  const [error, setError] = useState("");
  const [report, setReport] = useState(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const params = {};
      if (filters.task_name) params.task_name = filters.task_name;
      if (filters.quality) params.quality = filters.quality;
      if (filters.robot_id) params.robot_id = filters.robot_id;
      setRows(await api.listEpisodes({ ...params, limit: 100 }));
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters]);

  async function importFile(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      setReport(await api.importEpisodes(file));
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
      event.target.value = "";
    }
  }

  return (
    <div>
      <h1>Episodes</h1>
      {error && <p className="error">{error}</p>}

      <div className="card">
        <strong>Import CSV export</strong>
        <p className="muted">
          Idempotent: re-running the same file updates rather than duplicates.
          Skipped rows are reported with reasons.
        </p>
        <input
          type="file"
          accept=".csv"
          onChange={importFile}
          disabled={busy}
        />
        {report && (
          <p>
            <strong>
              {report.imported} imported, {report.updated} updated,{" "}
              {report.skipped} skipped
            </strong>{" "}
            of {report.rows_seen} rows.
            {report.skipped > 0 && (
              <details>
                <summary className="muted">skipped rows</summary>
                <ul>
                  {report.rows
                    .filter((r) => r.action === "skipped")
                    .map((r) => (
                      <li key={r.row_number}>
                        line {r.row_number} ({r.episode_id ?? "no id"}):{" "}
                        {r.reason}
                      </li>
                    ))}
                </ul>
              </details>
            )}
          </p>
        )}
      </div>

      <div className="card">
        <div className="row" style={{ marginBottom: 10 }}>
          <div>
            <label>Task name contains</label>
            <input
              value={filters.task_name}
              onChange={(e) =>
                setFilters({ ...filters, task_name: e.target.value })
              }
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
              <option value="bad">bad</option>
            </select>
          </div>
          <div>
            <label>Robot</label>
            <select
              value={filters.robot_id}
              onChange={(e) =>
                setFilters({ ...filters, robot_id: e.target.value })
              }
            >
              <option value="">any</option>
              {["arm-01", "arm-02", "arm-03", "mobile-01", "humanoid-01"].map(
                (r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ),
              )}
            </select>
          </div>
        </div>
        <table>
          <thead>
            <tr>
              <th>Episode</th>
              <th>Task</th>
              <th>Robot</th>
              <th>Recorded</th>
              <th>Duration</th>
              <th>Quality</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((ep) => (
              <tr key={ep.id}>
                <td>{ep.episode_id}</td>
                <td>{ep.task_name}</td>
                <td>{ep.robot_id}</td>
                <td>{new Date(ep.recorded_at).toLocaleDateString()}</td>
                <td>{ep.duration_seconds}s</td>
                <td>
                  <span className={`badge ${ep.quality}`}>{ep.quality}</span>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan="6" className="muted">
                  No episodes. Import seed/episodes.csv above.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
