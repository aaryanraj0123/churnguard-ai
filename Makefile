.PHONY: up up-d down down-v logs logs-all test test-all shell train migrate

up:
	docker compose up --build

up-d:
	docker compose up --build -d

down:
	docker compose down --remove-orphans

down-v:
	docker compose down --remove-orphans -v

logs:
	docker compose logs -f app frontend

logs-all:
	docker compose logs -f

test:
	docker compose exec app pytest tests/unit/ -v

test-all:
	docker compose exec app pytest tests/ -v --cov=app --cov-report=term-missing

shell:
	docker compose exec app bash

train:
	docker compose exec app python app/ml/train.py \
		--data-path data/train.csv \
		--output v1 --estimator rf --min-auc 0.75

migrate:
	docker compose exec app alembic upgrade head
