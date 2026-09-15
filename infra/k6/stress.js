// Feature 28 stress campaign: spike and soak scenarios against fake providers.
//
// infra/k6/release.js already proved feature 27's steady-state capacity
// target (500 VUs / 2 minutes). This script goes further: it ramps sharply
// (spike) and holds a sustained mixed read/write load (soak) against the
// same gateway-authenticated endpoints a real session uses — auth, session
// lookup, conversation listing, the M11 section catalog, document listing on
// a seeded conversation, and probe-job creation plus status polling for
// queue-drain visibility. It never calls a real provider: the release
// profile keeps WORKER_CHAT_PROVIDER and WORKER_EMBEDDING_PROVIDER on "fake".
//
// Optional env vars point iterations at a real seeded tenant (see
// scripts/seed_stress_corpus.py's seed-summary.json) so list responses are
// realistically sized instead of empty:
//   SEED_EMAIL, SEED_PASSWORD, SEED_ORGANIZATION_ID, SEED_CONVERSATION_ID
// Without them, setup() registers one throwaway account, exactly like
// release.js, so this script also runs standalone.

import http from "k6/http";
import { check, sleep } from "k6";

const BASE = __ENV.BASE_URL || "http://127.0.0.1:8000";
const P95_MS = __ENV.K6_P95_MS || "3000";
const SPIKE_PEAK_VUS = Number(__ENV.STRESS_SPIKE_VUS || 40);
const SOAK_VUS = Number(__ENV.STRESS_SOAK_VUS || 15);
const SOAK_DURATION = __ENV.STRESS_SOAK_DURATION || "90s";
const JOB_POLL_EVERY_N_ITERATIONS = 5;

export const options = {
  scenarios: {
    spike: {
      executor: "ramping-vus",
      exec: "iteration",
      startVUs: 0,
      stages: [
        { duration: "10s", target: SPIKE_PEAK_VUS },
        { duration: "20s", target: SPIKE_PEAK_VUS },
        { duration: "10s", target: 0 },
      ],
    },
    soak: {
      executor: "constant-vus",
      exec: "iteration",
      vus: SOAK_VUS,
      duration: SOAK_DURATION,
      startTime: "45s",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.02"],
    http_req_duration: [`p(95)<${P95_MS}`],
  },
};

function registerFreshTenant() {
  const email = `k6-stress-${Date.now()}-${__VU}@example.com`;
  const password = "a valid research stress passphrase";
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
  const token = login.json("access_token");
  const org = http.post(
    `${BASE}/v1/organizations`,
    JSON.stringify({ name: "k6 stress org" }),
    { headers: { ...headers, Authorization: `Bearer ${token}` } },
  );
  check(org, { "organization 201": (response) => response.status === 201 });
  const authHeaders = {
    Authorization: `Bearer ${token}`,
    "X-Organization-ID": org.json("id"),
  };
  const conversation = http.post(
    `${BASE}/v1/ai/conversations`,
    JSON.stringify({ title: "k6 stress conversation" }),
    { headers: { ...authHeaders, "Content-Type": "application/json" } },
  );
  check(conversation, {
    "conversation 201": (response) => response.status === 201,
  });
  return {
    token,
    organizationId: org.json("id"),
    conversationId: conversation.json("id"),
  };
}

function loginSeededTenant() {
  const headers = { "Content-Type": "application/json" };
  const login = http.post(
    `${BASE}/v1/auth/login`,
    JSON.stringify({ email: __ENV.SEED_EMAIL, password: __ENV.SEED_PASSWORD }),
    { headers },
  );
  check(login, { "seeded login 200": (response) => response.status === 200 });
  return {
    token: login.json("access_token"),
    organizationId: __ENV.SEED_ORGANIZATION_ID,
    conversationId: __ENV.SEED_CONVERSATION_ID,
  };
}

export function setup() {
  if (__ENV.SEED_EMAIL && __ENV.SEED_PASSWORD && __ENV.SEED_ORGANIZATION_ID) {
    return loginSeededTenant();
  }
  return registerFreshTenant();
}

export function iteration(data) {
  const authHeaders = {
    Authorization: `Bearer ${data.token}`,
    "X-Organization-ID": data.organizationId,
  };

  const live = http.get(`${BASE}/health/live`);
  check(live, { "live 200": (response) => response.status === 200 });

  const me = http.get(`${BASE}/v1/auth/me`, { headers: authHeaders });
  check(me, { "me 200": (response) => response.status === 200 });

  const conversations = http.get(`${BASE}/v1/ai/conversations?limit=20`, {
    headers: authHeaders,
  });
  check(conversations, {
    "conversations 200": (response) => response.status === 200,
  });

  const catalog = http.get(`${BASE}/v1/ai/m11/sections/catalog`, {
    headers: authHeaders,
  });
  check(catalog, { "m11 catalog 200": (response) => response.status === 200 });

  if (data.conversationId) {
    const documents = http.get(
      `${BASE}/v1/ai/conversations/${data.conversationId}/documents?limit=20`,
      { headers: authHeaders },
    );
    check(documents, {
      "documents 200": (response) => response.status === 200,
    });
  }

  if (__ITER % JOB_POLL_EVERY_N_ITERATIONS === 0) {
    const created = http.post(
      `${BASE}/v1/jobs`,
      JSON.stringify({ kind: "probe" }),
      { headers: { ...authHeaders, "Content-Type": "application/json" } },
    );
    check(created, { "probe job 202": (response) => response.status === 202 });
    if (created.status === 202) {
      const jobId = created.json("id");
      const status = http.get(`${BASE}/v1/jobs/${jobId}`, {
        headers: authHeaders,
      });
      check(status, { "job status 200": (response) => response.status === 200 });
    }
  }

  sleep(1);
}
