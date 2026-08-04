import http from 'k6/http';
import { check, sleep } from 'k6';
import { BASE_URL, getHeaders } from './config.js';

export const options = {
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

function generateIdempotencyKey() {
  return `${Date.now()}-${Math.floor(Math.random() * 1000000)}`;
}

export default function () {
  // 1. Get products
  const listRes = http.get(`${BASE_URL}/api/v1/products`, { headers: getHeaders() });
  check(listRes, { 'GET /products is 200': (r) => r.status === 200 });
  
  if (listRes.status !== 200) {
    return;
  }

  let products = [];
  try {
    products = JSON.parse(listRes.body);
  } catch(e) {}

  if (products.length === 0) {
    console.warn('No products found to place order.');
    return;
  }

  const selectedProduct = products[0];

  // 2. Place an order
  const orderPayload = {
    productId: selectedProduct.id,
    quantity: 1,
    // Add loadTest flag to ensure SES skips emailing
    isLoadTest: true,
    message_attributes: { loadTest: true }
  };

  const headers = getHeaders();
  headers['Idempotency-Key'] = generateIdempotencyKey();

  const orderRes = http.post(`${BASE_URL}/api/v1/orders`, JSON.stringify(orderPayload), { headers });
  check(orderRes, { 'POST /orders is successful (200/201/202)': (r) => r.status >= 200 && r.status < 300 });

  if (orderRes.status >= 200 && orderRes.status < 300) {
    let order;
    try {
      order = JSON.parse(orderRes.body);
    } catch(e) {}
    
    if (order && order.id) {
      // 3. Check order status (Saga verification)
      sleep(2); // wait for initial processing
      const statusRes = http.get(`${BASE_URL}/api/v1/orders/${order.id}`, { headers: getHeaders() });
      check(statusRes, { 
        'GET /orders/{id} is 200': (r) => r.status === 200,
        'order status is PENDING or processing': (r) => {
          try {
            const body = JSON.parse(r.body);
            return body.status === 'PENDING' || body.status === 'PROCESSING' || body.status === 'CREATED';
          } catch(e) {
            return false;
          }
        }
      });
    }
  }

  sleep(5); // Sleep to limit order creation rate even during smoke test
}
