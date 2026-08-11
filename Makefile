.PHONY: up down reset build test deploy destroy park unpark scale-down scale-up

up:
	docker compose up --build

up-bg:
	docker compose up --build -d

down:
	docker compose down

reset:
	docker compose down -v
	docker compose up --build

build:
	docker compose build --no-cache

SERVICES := common user-service order-service inventory-service product-service notification-lambda reconciliation-lambda ws-authorizer-lambda ws-connect-lambda ws-disconnect-lambda ws-push-lambda order-outbox-publisher

test:
	@for s in $(SERVICES); do \
	  if ls services/$$s/tests/test_*.py >/dev/null 2>&1; then \
	    echo "===== $$s ====="; \
	    (cd "services/$$s" && python -m pytest) || exit 1; \
	  else \
	    echo "===== $$s (no tests yet, skipped) ====="; \
	  fi; \
	done

lambda-build:
	powershell -ExecutionPolicy Bypass -File scripts/build-lambda-packages.ps1

deploy: lambda-build
	cd infra && terraform init && terraform apply

destroy:
	cd infra && terraform destroy

park: lambda-build
	cd infra && terraform apply -var="live=false"

unpark: lambda-build
	cd infra && terraform apply -var="live=true"

scale-down:
	aws ecs update-service --cluster smartretailx-cluster --service smartretailx-order-service --desired-count 0 --region eu-west-1
	aws ecs update-service --cluster smartretailx-cluster --service smartretailx-inventory-service --desired-count 0 --region eu-west-1
	aws ecs update-service --cluster smartretailx-cluster --service smartretailx-user-service --desired-count 0 --region eu-west-1
	aws ecs update-service --cluster smartretailx-cluster --service smartretailx-product-service --desired-count 0 --region eu-west-1

scale-up:
	aws ecs update-service --cluster smartretailx-cluster --service smartretailx-order-service --desired-count 1 --region eu-west-1
	aws ecs update-service --cluster smartretailx-cluster --service smartretailx-inventory-service --desired-count 1 --region eu-west-1
	aws ecs update-service --cluster smartretailx-cluster --service smartretailx-user-service --desired-count 1 --region eu-west-1
	aws ecs update-service --cluster smartretailx-cluster --service smartretailx-product-service --desired-count 1 --region eu-west-1
