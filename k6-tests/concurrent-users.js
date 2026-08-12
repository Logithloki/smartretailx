import http from 'k6/http';
import { check, sleep } from 'k6';
import { BASE_URL, getHeaders, productsFrom, validateConfig } from './config.js';

export const options = {
  scenarios: {
    concurrent_catalogue_users: {
      executor: 'constant-vus',
      vus: Number(__ENV.CONCURRENT_USERS || 25),
      duration: __ENV.DURATION || '5m',
    },
  },
  summaryTrendStats: ['min', 'med', 'avg', 'p(90)', 'p(95)', 'p(99)', 'max', 'count'],
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<750', 'p(99)<1500'],
  },
  tags: { test_type: 'concurrent-users', project: 'smartretailx' },
};

export function setup() {
  return validateConfig();
}

export default function () {
  const list = http.get(`${BASE_URL}/v1/products`, {
    headers: getHeaders(),
    tags: { name: 'ConcurrentProductsList' },
  });
  check(list, { 'catalogue list is 200': (response) => response.status === 200 });
  const products = productsFrom(list);
  if (products.length) {
    const product = products[(__VU + __ITER) % products.length];
    const detail = http.get(`${BASE_URL}/v1/products/${product.productId}`, {
      headers: getHeaders(),
      tags: { name: 'ConcurrentProductDetail' },
    });
    check(detail, { 'catalogue detail is 200': (response) => response.status === 200 });
  }
  sleep(1);
}
