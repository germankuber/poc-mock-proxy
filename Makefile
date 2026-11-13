LANGS := python go java rust dotnet

.DEFAULT_GOAL := help

.PHONY: help certs build up down test $(addprefix test-,$(LANGS)) mock-on mock-off logs ps clean

help:
	@echo "certs        generate certificates"
	@echo "build        build all images"
	@echo "up           generate certificates, build and start every service"
	@echo "down         stop every service"
	@echo "test         run the five cases for every language"
	@echo "test-<lang>  run the five cases for one language ($(LANGS))"
	@echo "mock-on      enable the mock in the proxy"
	@echo "mock-off     disable the mock in the proxy"
	@echo "logs         follow service logs"
	@echo "ps           list services"
	@echo "clean        down and remove generated certificates"

certs:
	./scripts/gen-certs.sh

build:
	./scripts/build-images.sh

up: certs build
	docker compose up -d --force-recreate --remove-orphans

down:
	docker compose down --remove-orphans

test:
	python3 run_poc.py

$(addprefix test-,$(LANGS)): test-%:
	python3 run_poc.py $* --no-up

mock-on:
	./scripts/toggle.sh on

mock-off:
	./scripts/toggle.sh off

logs:
	docker compose logs -f --tail=50

ps:
	docker compose ps

clean: down
	find certs -mindepth 1 ! -name .gitkeep -delete
