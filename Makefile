DOCKER := $(shell { command -v podman || command -v docker; })
TIMESTAMP := $(shell date -u +"%Y%m%d%H%M")
COMMIT := $(shell git rev-parse --short HEAD 2>/dev/null)
ifeq ($(shell uname),Darwin)
SELINUX1 :=
SELINUX2 :=
else
SELINUX1 := :z
SELINUX2 := ,z
endif

.PHONY: all left draw clean_firmware clean_image clean

all:
	$(shell bin/get_version_local.sh clique >> /dev/null)
	$(DOCKER) build --tag zmk --file Dockerfile .
	$(DOCKER) run --rm -it --name zmk \
		-v $(PWD)/firmware:/app/firmware$(SELINUX1) \
		-v $(PWD)/config:/app/config:ro$(SELINUX2) \
		-e TIMESTAMP=$(TIMESTAMP) \
		-e COMMIT=$(COMMIT) \
		-e BUILD_RIGHT=true \
		zmk
	git checkout config/version.dtsi

left:
	$(shell bin/get_version_local.sh clique >> /dev/null)
	$(DOCKER) build --tag zmk --file Dockerfile .
	$(DOCKER) run --rm -it --name zmk \
		-v $(PWD)/firmware:/app/firmware$(SELINUX1) \
		-v $(PWD)/config:/app/config:ro$(SELINUX2) \
		-e TIMESTAMP=$(TIMESTAMP) \
		-e COMMIT=$(COMMIT) \
		-e BUILD_RIGHT=false \
		zmk
	git checkout config/version.dtsi

# Keymap drawing, finger_* layers (bilateral HRM internals) are skipped
DRAWER := uvx --from keymap-drawer==0.23.0 keymap -c keymap_drawer.config.yaml

draw:
	mkdir -p keymap-drawer
	$(DRAWER) parse -z config/adv360.keymap > keymap-drawer/adv360.yaml
	$(DRAWER) draw keymap-drawer/adv360.yaml -z adv360 \
		-s $$(sed -nE 's/^  ([A-Za-z0-9_]+):$$/\1/p' keymap-drawer/adv360.yaml | grep -vE '^[LR](Index|Middle|Ring|Pinky)$$') \
		> keymap-drawer/adv360.svg

clean_firmware:
	rm -f firmware/*.uf2

clean_image:
	$(DOCKER) image rm zmk docker.io/zmkfirmware/zmk-build-arm:stable

clean: clean_firmware clean_image
