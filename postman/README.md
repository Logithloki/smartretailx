# Newman contract suite

The committed environment is a secret-free template. Supply fresh Cognito tokens at runtime:

```bash
newman run postman/SmartRetailX.postman_collection.json \
  -e postman/SmartRetailX.postman_environment.json \
  --env-var apiBaseUrl=https://example.cloudfront.net \
  --env-var customerToken="$CUSTOMER_TOKEN" \
  --env-var adminToken="$ADMIN_TOKEN" \
  --reporters cli,junit --reporter-junit-export newman-results.xml
```

Never persist exported tokens or generated environment files in the repository.
