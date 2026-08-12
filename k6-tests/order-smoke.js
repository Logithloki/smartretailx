import http from 'k6/http';
import { check, sleep } from 'k6';
import { BASE_URL, getHeaders, productsFrom, validateConfig } from './config.js';

export const options = {
  summaryTrendStats: ['min', 'med', 'avg', 'p(90)', 'p(95)', 'p(99)', 'max', 'count'],
  vus: 2,
  duration: '1m',
  thresholds: {
    'http_req_failed': ['rate==0'],
  },
  tags: {
    test_type: 'smoke',
    project: 'smartretailx',
  },
};

export function setup() {
  return validateConfig();
}

function generateIdempotencyKey() {
  return `${Date.now()}-${Math.floor(Math.random() * 1000000)}`;
}

export default function () {
  // 1. Get products
  const listRes = http.get(`${BASE_URL}/v1/products`, { headers: getHeaders() });
  check(listRes, { 'GET /products is 200': (r) => r.status === 200 });
  
  if (listRes.status !== 200) {
    return;
  }

  const products = productsFrom(listRes);

  if (products.length === 0) {
    console.warn('No products found to place order.');
    return;
  }

  const selectedProduct = products[0];

  // 2. Place an order
  const orderPayload = {
    items: [{
      productId: selectedProduct.productId,
      quantity: 1,
    }],
    loadTest: true,
  };

  const headers = getHeaders();
  headers['Idempotency-Key'] = generateIdempotencyKey();

  const orderRes = http.post(`${BASE_URL}/v1/orders`, JSON.stringify(orderPayload), { headers });
  check(orderRes, { 'POST /orders is successful (200/201/202)': (r) => r.status >= 200 && r.status < 300 });

  if (orderRes.status >= 200 && orderRes.status < 300) {
    let order;
    try {
      order = JSON.parse(orderRes.body);
    } catch(e) {}
    
    if (order && order.orderId) {
      // 3. Check order status (Saga verification)
      sleep(2); // wait for initial processing
      const statusRes = http.get(`${BASE_URL}/v1/orders/${order.orderId}`, { headers: getHeaders() });
      check(statusRes, { 
        'GET /orders/{id} is 200': (r) => r.status === 200,
        'order status is PENDING or processing': (r) => {
          try {
            const body = JSON.parse(r.body);
            return ['PENDING', 'CONFIRMED', 'REJECTED'].includes(body.status);
          } catch(e) {
            return false;
          }
        }
      });
    }
  }

  sleep(5); // Sleep to limit order creation rate even during smoke test
}
