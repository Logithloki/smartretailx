import http from 'k6/http';
import { check, sleep } from 'k6';
import { BASE_URL, getHeaders } from './config.js';

/**
 * Cache-Busting Stress Test
 * 
 * Bypasses CloudFront edge cache by appending a unique query parameter
 * to every request, forcing all traffic through to ECS containers.
 * This causes real CPU utilization spikes on the backend.
 */
export const options = {
  stages: [
    { duration: '1m', target: 50 },   // Warm up
    { duration: '2m', target: 150 },   // Ramp to heavy
    { duration: '3m', target: 200 },   // Sustained heavy load — CPU should spike here
    { duration: '1m', target: 0 },     // Cool down
  ],
  thresholds: {
    'http_req_failed': ['rate<0.2'],       // Allow up to 20% errors under extreme stress
    'http_req_duration': ['p(95)<5000'],    // Relaxed — we want to find the breaking point
  },
  tags: {
    test_type: 'cache-bust-stress',
    project: 'smartretailx',
  },
};

let counter = 0;

export default function () {
  counter++;
  // Unique cache-buster param ensures CloudFront treats every request as a cache MISS
  const cacheBuster = `${Date.now()}-${__VU}-${__ITER}-${counter}`;

  const res = http.get(
    `${BASE_URL}/api/v1/products?_cb=${cacheBuster}`,
    { headers: getHeaders() }
  );

  check(res, {
    'status is 200': (r) => r.status === 200,
  });

  // Very short sleep to maximize throughput per VU
  sleep(0.2);
}
