CXX ?= g++
CXXFLAGS = -std=c++17 -Wall -Wextra -Werror -I../../

BUILD_DIR = build
HOST_TESTS = $(BUILD_DIR)/test_placeholder
CONTRACT_TOOL = $(BUILD_DIR)/contract_checker

all: $(HOST_TESTS) contract_checker

$(BUILD_DIR)/test_placeholder: test_placeholder.cpp ../../config/calibration.h ../../platform/pins.h
	@mkdir -p $(BUILD_DIR)
	$(CXX) $(CXXFLAGS) -o $@ $<
	./$@

contract_checker: $(CONTRACT_TOOL)

$(CONTRACT_TOOL): contract_checker.cpp protocol_parser.cpp protocol_parser.h
	@mkdir -p $(BUILD_DIR)
	$(CXX) $(CXXFLAGS) -o $@ contract_checker.cpp protocol_parser.cpp

clean:
	rm -rf $(BUILD_DIR)

.PHONY: all contract_checker clean