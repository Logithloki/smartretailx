export const BASE_URL = (__ENV.BASE_URL || '').replace(/\/$/, '');
export const AUTH_TOKEN = __ENV.AUTH_TOKEN || '';

export function validateConfig() {
  if (!BASE_URL.startsWith('https://') && !BASE_URL.startsWith('http://localhost')) {
    throw new Error('BASE_URL must be an HTTPS origin (or localhost)');
  }
  if (!AUTH_TOKEN || AUTH_TOKEN === 'MISSING_TOKEN') {
    throw new Error('AUTH_TOKEN must contain a current Cognito access token');
  }
  return { startedAt: new Date().toISOString() };
}

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

export function productsFrom(res) {
  try {
    const body = res.json();
    return Array.isArray(body.products) ? body.products : [];
  } catch (_) {
    return [];
  }
}
