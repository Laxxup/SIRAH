# Host-side build for firmware logic that must run WITHOUT Arduino
# (ADR-0010, decision P3: plain g++ C++17 is the host toolchain).
#
# Targets:
#   all             build + run core tests and the contract checker
#   core_tests      build + run firmware core tests
#   contract_checker  build the golden-corpus gate binary
#   clean

CXX ?= g++
CXXFLAGS = -std=c++17 -Wall -Wextra -Werror -I../../

BUILD_DIR = build
HOST_TESTS = $(BUILD_DIR)/core_tests
CONTRACT_TOOL = $(BUILD_DIR)/contract_checker

CORE_SRCS = \
	../../core/protocol.cpp \
	../../core/mapping.cpp \
	../../core/easing.cpp \
	../../core/blink_fsm.cpp

all: core_tests contract_checker

core_tests: $(HOST_TESTS)
	./$(HOST_TESTS)

$(BUILD_DIR)/core_tests: core_tests.cpp $(CORE_SRCS)
	@mkdir -p $(BUILD_DIR)
	$(CXX) $(CXXFLAGS) -o $@ core_tests.cpp $(CORE_SRCS)

contract_checker: $(CONTRACT_TOOL)

$(CONTRACT_TOOL): contract_checker.cpp ../../core/protocol.cpp
	@mkdir -p $(BUILD_DIR)
	$(CXX) $(CXXFLAGS) -o $@ contract_checker.cpp ../../core/protocol.cpp

clean:
	rm -rf $(BUILD_DIR)

.PHONY: all core_tests contract_checker clean
