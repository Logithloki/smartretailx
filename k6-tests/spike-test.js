import http from 'k6/http';
import { check, sleep } from 'k6';
import { BASE_URL, getHeaders } from './config.js';

export const options = {
  stages: [
    { duration: '1m', target: 5 }, // Baseline
    { duration: '1m', target: 150 }, // Sudden spike
    { duration: '3m', target: 5 }, // Recovery phase
  ],
  thresholds: {
    // Focus on recovery behavior
    'http_req_failed': ['rate<0.05'], 
    'http_req_duration': ['p(95)<1000'],
  },
  tags: {
    test_type: 'spike',
    project: 'smartretailx',
  },
};

export default function () {
  const res = http.get(`${BASE_URL}/api/v1/products`, { headers: getHeaders() });
  check(res, { 'status is 200': (r) => r.status === 200 });
  sleep(1);
}
