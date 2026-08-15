import http from "k6/http";
import { check, sleep } from "k6";

const BASE = __ENV.BASE_URL || "http://127.0.0.1:8000";
const P95_MS = __ENV.K6_P95_MS || "2000";

export const options = {
  vus: Number(__ENV.K6_VUS || 20),
  duration: __ENV.K6_DURATION || "30s",
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: [`p(95)<${P95_MS}`],
  },
};

export function setup() {
  const email = `k6-${Date.now()}@example.com`;
  const password = "a valid research passphrase";
  const headers = { "Content-Type": "application/json" };
  const register = http.post(
    `${BASE}/v1/auth/register`,
    JSON.stringify({ email, password }),
    { headers },
  );
  check(register, { "register 201": (response) => response.status === 201 });
  const login = http.post(
    `${BASE}/v1/auth/login`,
    JSON.stringify({ email, password }),
    { headers },
  );
  check(login, { "login 200": (response) => response.status === 200 });
  return { token: login.json("access_token") };
}

export default function (data) {
  const live = http.get(`${BASE}/health/live`);
  check(live, { "live 200": (response) => response.status === 200 });
  const me = http.get(`${BASE}/v1/auth/me`, {
    headers: { Authorization: `Bearer ${data.token}` },
  });
  check(me, { "me 200": (response) => response.status === 200 });
  sleep(1);
}
