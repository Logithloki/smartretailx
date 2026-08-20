# Test ECS self-healing evidence

Date: 20 August 2026
Environment: Test
Target: `smartretailx-test-product-service`
Result: PASS

Exactly one running product-service task was stopped while authenticated catalogue traffic was active. The ECS service desired count remained one. ECS scheduled a different task and restored `runningCount == desiredCount` with no pending task in 81.9 seconds.

No service configuration, desired count, Terraform state, data store, Staging resource or Production resource was changed. The machine-readable timestamps and task identifiers are in `ecs-task-recovery.json`.

Because this demo environment runs one task per service, the experiment demonstrates automatic replacement rather than a claim of guaranteed zero-downtime service during abrupt task loss.
