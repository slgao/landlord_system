import axios from "axios";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const api = axios.create({ baseURL: BASE });

api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("token");
    if (token) config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401 && typeof window !== "undefined") {
      localStorage.removeItem("token");
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

export async function login(username: string, password: string) {
  const res = await axios.post(`${BASE}/api/auth/token`, { username, password });
  const token: string = res.data.access_token;
  localStorage.setItem("token", token);
  return token;
}

export function logout() {
  localStorage.removeItem("token");
  window.location.href = "/login";
}

export function isAuthenticated() {
  if (typeof window === "undefined") return false;
  return !!localStorage.getItem("token");
}
