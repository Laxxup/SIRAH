.PHONY: fmt-check mod-check test-headless vet-headless test-opencv4 \
	test-race-opencv4 vet-opencv4 build-opencv4 check-generated \
	verify-model test-firmware-host check-firmware check check-opencv4

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

test-opencv4:
	CGO_ENABLED=1 go test -tags opencv4 -buildvcs=false -mod=readonly ./...

test-race-opencv4:
	CGO_ENABLED=1 go test -race -tags opencv4 -buildvcs=false -mod=readonly ./...

vet-opencv4:
	CGO_ENABLED=1 go vet -tags opencv4 -mod=readonly ./...

build-opencv4:
	CGO_ENABLED=1 go build -tags opencv4 -buildvcs=false -mod=readonly ./cmd/sirah ./cmd/vision

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

check-opencv4: test-opencv4 test-race-opencv4 vet-opencv4 build-opencv4
