CXX ?= g++
CXXFLAGS = -std=c++17 -Wall -Wextra -Werror -I../../

BUILD_DIR = build
HOST_TESTS = $(BUILD_DIR)/test_placeholder

all: $(HOST_TESTS)

$(BUILD_DIR)/test_placeholder: test_placeholder.cpp ../../config/calibration.h ../../platform/pins.h
	@mkdir -p $(BUILD_DIR)
	$(CXX) $(CXXFLAGS) -o $@ $<
	./$@

clean:
	rm -rf $(BUILD_DIR)

.PHONY: all clean