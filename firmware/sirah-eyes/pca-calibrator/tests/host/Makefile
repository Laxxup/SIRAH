CXX := g++
CXXFLAGS := -std=c++17 -Wall -Wextra -Werror -I../..
BUILD := build
TARGET := $(BUILD)/test_calibration_commands

.PHONY: test clean

test: $(TARGET)
	./$(TARGET)

$(TARGET): test_calibration_commands.cpp ../../calibration_commands.h | $(BUILD)
	$(CXX) $(CXXFLAGS) -o $@ $<

$(BUILD):
	mkdir -p $@

clean:
	rm -rf $(BUILD)
