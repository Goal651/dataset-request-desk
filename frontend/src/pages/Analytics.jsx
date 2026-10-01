import { useEffect, useState } from "react";
import { api } from "../api";

function todayMinus(days) {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return date.toISOString().slice(0, 10);
}

export default function AnalyticsPage() {
  const [range, setRange] = useState({
    from: todayMinus(60),
    to: todayMinus(0),
  });
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .analytics(range.from, range.to)
      .then(setData)
      .catch((err) => setError(err.message));
  }, [range]);

  return (
    <div>
      <h1>Analytics</h1>
      {error && <p className="error">{error}</p>}

      <div className="card row">
        <div>
          <label>From</label>
          <input
            type="date"
            value={range.from}
            onChange={(e) => setRange({ ...range, from: e.target.value })}
          />
        </div>
        <div>
          <label>To</label>
          <input
            type="date"
            value={range.to}
            onChange={(e) => setRange({ ...range, to: e.target.value })}
          />
        </div>
      </div>

      {data && (
        <>
          <div className="card">
            <strong>Episodes per day per robot</strong>
            <table>
              <thead>
                <tr>
                  <th>Day</th>
                  <th>Robot</th>
                  <th>Episodes recorded</th>
                </tr>
              </thead>
              <tbody>
                {data.episodes_per_day_per_robot.map((row) => (
                  <tr key={`${row.day}-${row.robot_id}`}>
                    <td>{row.day}</td>
                    <td>{row.robot_id}</td>
                    <td>{row.episodes_recorded}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="card kv">
            <strong style={{ gridColumn: "1 / -1" }}>Request fulfilment</strong>
            {Object.entries(data.fulfilment.status_counts).map(
              ([status, count]) => (
                <span key={status} style={{ display: "contents" }}>
                  <span className="muted">{status}</span>
                  <span>{count}</span>
                </span>
              ),
            )}
            <span className="muted">median submitted → delivered</span>
            <span>
              {data.fulfilment.median_submitted_to_delivered_hours === null
                ? "no deliveries yet"
                : `${data.fulfilment.median_submitted_to_delivered_hours} h`}
            </span>
          </div>

          <div className="card">
            <strong>Top 5 tasks by good episodes</strong>
            <table>
              <thead>
                <tr>
                  <th>Task</th>
                  <th>Good episodes</th>
                </tr>
              </thead>
              <tbody>
                {data.top_tasks.map((task) => (
                  <tr key={task.task_name}>
                    <td>{task.task_name}</td>
                    <td>{task.good_episodes}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
