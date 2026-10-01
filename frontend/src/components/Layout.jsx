import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const isStaff = user.role === "operator" || user.role === "admin";

  return (
    <div>
      <nav className="nav">
        <span className="brand">Dataset Request Desk</span>
        <div className="links">
          <NavLink to="/">Requests</NavLink>
          {isStaff && <NavLink to="/episodes">Episodes</NavLink>}
          {isStaff && <NavLink to="/analytics">Analytics</NavLink>}
          {user.role === "admin" && <NavLink to="/users">Users</NavLink>}
        </div>
        <span className="who">
          {user.name} · {user.role}
        </span>
        <button
          className="secondary"
          onClick={() => {
            logout();
            navigate("/login");
          }}
        >
          Log out
        </button>
      </nav>
      <div className="page">
        <Outlet />
      </div>
    </div>
  );
}
