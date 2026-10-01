const TOKEN_KEY = "drd_token";
const USER_KEY = "drd_user";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function getStoredUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY));
  } catch {
    return null;
  }
}

export function storeSession(token, user) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

async function request(method, path, body, isForm = false) {
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body && !isForm) headers["Content-Type"] = "application/json";

  const response = await fetch(`/api${path}`, {
    method,
    headers,
    body: isForm ? body : body ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
    let detail = `${response.status}`;
    try {
      const data = await response.json();
      detail =
        typeof data.detail === "string"
          ? data.detail
          : JSON.stringify(data.detail);
    } catch {
      /* keep status code */
    }
    if (response.status === 401) clearSession();
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return null;
  return response.json();
}

export const api = {
  login: (email, password) =>
    request("POST", "/auth/login", { email, password }),
  me: () => request("GET", "/auth/me"),
  listUsers: () => request("GET", "/users"),
  createUser: (payload) => request("POST", "/users", payload),
  updateUser: (id, payload) => request("PATCH", `/users/${id}`, payload),

  listEpisodes: (params) =>
    request("GET", `/episodes?${new URLSearchParams(params)}`),
  importEpisodes: (file) => {
    const form = new FormData();
    form.append("file", file);
    return request("POST", "/episodes/import", form, true);
  },

  listRequests: (status) =>
    request("GET", `/requests${status ? `?status=${status}` : ""}`),
  getRequest: (id) => request("GET", `/requests/${id}`),
  createRequest: (payload) => request("POST", "/requests", payload),
  transition: (id, to_status, note) =>
    request("POST", `/requests/${id}/transition`, {
      to_status,
      note: note || null,
    }),

  assign: (requestId, episodePk) =>
    request("POST", `/requests/${requestId}/assignments`, {
      episode_pk: episodePk,
    }),
  unassign: (requestId, assignmentId) =>
    request("DELETE", `/requests/${requestId}/assignments/${assignmentId}`),
  listExports: (requestId) => request("GET", `/requests/${requestId}/exports`),
  retryExport: (requestId, jobId) =>
    request("POST", `/requests/${requestId}/exports/${jobId}/retry`),

  analytics: (from, to) => request("GET", `/analytics?from=${from}&to=${to}`),
};
