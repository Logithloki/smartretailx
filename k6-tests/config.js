import { check } from 'k6';

export const BASE_URL = __ENV.BASE_URL || 'https://example.cloudfront.net';
export const AUTH_TOKEN = __ENV.AUTH_TOKEN || 'MISSING_TOKEN';

export const getHeaders = () => ({
  'Content-Type': 'application/json',
  'Authorization': `Bearer ${AUTH_TOKEN}`,
});

export function checkResponse(res, expectedStatus = 200) {
  const success = res.status === expectedStatus;
  if (!success) {
    console.error(`Request failed. Status: ${res.status}, Body: ${res.body}`);
  }
  return success;
}

export function getRandomElement(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}
