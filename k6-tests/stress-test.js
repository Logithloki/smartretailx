import http from 'k6/http';
import { check, sleep } from 'k6';
import { BASE_URL, getHeaders, validateConfig } from './config.js';

export const options = {
  summaryTrendStats: ['min', 'med', 'avg', 'p(90)', 'p(95)', 'p(99)', 'max', 'count'],
  stages: [
    { duration: '2m', target: 10 },
    { duration: '2m', target: 50 },
    { duration: '2m', target: 100 },
    { duration: '2m', target: 150 }, // Monitor ECS autoscaling to kick in here (CPU > 70%)
    { duration: '2m', target: 200 }, // API Gateway limits might start throttling here (rate=50, burst=100)
    { duration: '2m', target: 0 },
  ],
  thresholds: {
    // Relaxed thresholds since we want to find the breaking point
    'http_req_failed': ['rate<0.1'], 
    'http_req_duration': ['p(95)<2000'],
  },
  tags: {
    test_type: 'stress',
    project: 'smartretailx',
  },
};

export function setup() {
  return validateConfig();
}

export default function () {
  const rand = Math.random();
  
  if (rand < 0.7) {
    const res = http.get(`${BASE_URL}/v1/products`, { headers: getHeaders() });
    check(res, { 'status is 200': (r) => r.status === 200 });
  } else {
    // Pick a hardcoded ID or random UUID to stress the DB without needing a list fetch
    const randomId = `prod-${Math.floor(Math.random() * 100)}`;
    const res = http.get(`${BASE_URL}/v1/products/${randomId}`, { headers: getHeaders() });
    // Don't strictly check for 200 because product might not exist, check for valid API response
    check(res, { 'status is valid': (r) => r.status === 200 || r.status === 404 });
  }

  // Smaller sleep to generate higher throughput per VU
  sleep(0.5);
}
