import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate } from 'k6/metrics';
import { BASE_URL, getHeaders, productsFrom, validateConfig } from './config.js';

export const options = {
  summaryTrendStats: ['min', 'med', 'avg', 'p(90)', 'p(95)', 'p(99)', 'max', 'count'],
  stages: [
    { duration: '2m', target: 50 }, // Ramp up to 50 VUs
    { duration: '10m', target: 50 }, // Hold at 50 VUs for 10m
    { duration: '2m', target: 0 }, // Ramp down to 0 VUs
  ],
  thresholds: {
    'http_req_duration': ['p(95)<500', 'avg<200'], // p95 under 500ms, avg under 200ms
    'http_req_failed': ['rate<0.01'], // error rate < 1%
    'product_list_duration': ['p(95)<500'],
    'product_detail_duration': ['p(95)<400'],
  },
  tags: {
    test_type: 'load',
    project: 'smartretailx',
  },
};

export function setup() {
  return validateConfig();
}

const productListDuration = new Trend('product_list_duration');
const productDetailDuration = new Trend('product_detail_duration');
const errorRate = new Rate('errors');

export default function () {
  const rand = Math.random();
  
  if (rand < 0.7) {
    // 70% traffic to product list
    const res = http.get(`${BASE_URL}/v1/products`, { headers: getHeaders(), tags: { name: 'ProductsList' } });
    productListDuration.add(res.timings.duration);
    const success = check(res, { 'status is 200': (r) => r.status === 200 });
    errorRate.add(!success);
    if (!success) console.warn(`List API error: ${res.status}`);
  } else {
    // 30% traffic to product detail, simulating realistic navigation
    // Typically you'd fetch list then pick an ID, but for load testing we can just pick a known ID or fetch list first
    const listRes = http.get(`${BASE_URL}/v1/products`, { headers: getHeaders(), tags: { name: 'ProductsListForDetail' } });
    if (listRes.status === 200) {
      const products = productsFrom(listRes);
      
      if (products && products.length > 0) {
        const product = products[Math.floor(Math.random() * products.length)];
        const res = http.get(`${BASE_URL}/v1/products/${product.productId}`, { headers: getHeaders(), tags: { name: 'ProductDetail' } });
        productDetailDuration.add(res.timings.duration);
        const success = check(res, { 'status is 200': (r) => r.status === 200 });
        errorRate.add(!success);
      }
    }
  }

  sleep(1);
}
