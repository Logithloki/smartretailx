import http from 'k6/http';
import { check, sleep } from 'k6';
import { BASE_URL, getHeaders, validateConfig } from './config.js';

export const options = {
  summaryTrendStats: ['min', 'med', 'avg', 'p(90)', 'p(95)', 'p(99)', 'max', 'count'],
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

export function setup() {
  return validateConfig();
}

export default function () {
  const res = http.get(`${BASE_URL}/v1/products`, { headers: getHeaders() });
  check(res, { 'status is 200': (r) => r.status === 200 });
  sleep(1);
}
