.PHONY: fmt-check mod-check test-headless vet-headless test-opencv \
	test-race-opencv vet-opencv build-opencv test-opencv5 vet-opencv5 \
	build-opencv5 check-generated verify-model test-firmware-host \
	check-firmware check check-opencv check-opencv5

fmt-check:
	@test -z "$$(gofmt -l $$(git ls-files '*.go'))" || { \
		gofmt -l $$(git ls-files '*.go'); \
		exit 1; \
	}

mod-check:
	go mod verify
	go mod tidy -diff

test-headless:
	CGO_ENABLED=0 go test -buildvcs=false -mod=readonly ./...

vet-headless:
	CGO_ENABLED=0 go vet -mod=readonly ./...

test-opencv:
	CGO_ENABLED=1 go test -buildvcs=false -mod=readonly -p 1 ./...

test-race-opencv:
	CGO_ENABLED=1 go test -race -buildvcs=false -mod=readonly -p 1 ./...

vet-opencv:
	CGO_ENABLED=1 go vet -mod=readonly ./...

build-opencv:
	CGO_ENABLED=1 go build -buildvcs=false -mod=readonly ./cmd/sirah ./cmd/vision

test-opencv5:
	CGO_ENABLED=1 go test -tags opencv5 -buildvcs=false -mod=readonly -p 1 ./...

vet-opencv5:
	CGO_ENABLED=1 go vet -tags opencv5 -mod=readonly ./...

build-opencv5:
	CGO_ENABLED=1 go build -tags opencv5 -buildvcs=false -mod=readonly ./cmd/sirah ./cmd/vision

check-generated:
	python3 scripts/generate_eyes_calibration.py --check
	python3 scripts/check_eyes_mapping.py

verify-model:
	sha256sum -c models/face_detection_yunet_2023mar.onnx.sha256

test-firmware-host:
	@tmp="$$(mktemp -d)"; trap 'rm -rf "$$tmp"' 0; \
		g++ -std=c++17 -Wall -Wextra -Werror \
			-I firmware/tests/one-servo \
			firmware/tests/one-servo/test.cpp -o "$$tmp/test_one"; \
		"$$tmp/test_one"; \
		g++ -std=c++17 -Wall -Wextra -Werror -DTEST_UNCONFIGURED \
			-I firmware/tests/one-servo \
			firmware/tests/one-servo/test.cpp -o "$$tmp/test_unconfigured"; \
		"$$tmp/test_unconfigured"

check-firmware:
	arduino-cli compile --fqbn esp32:esp32:esp32 firmware/sirah

check: fmt-check mod-check test-headless vet-headless check-generated verify-model test-firmware-host

check-opencv: test-opencv test-race-opencv vet-opencv build-opencv

check-opencv5: test-opencv5 vet-opencv5 build-opencv5
