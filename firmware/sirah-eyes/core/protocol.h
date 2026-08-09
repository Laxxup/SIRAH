// Shared wire-protocol layer for the ESP32 firmware.
//
// Parser: exact mirror of the Python parser (src/sirah/protocol/parse_line.py);
// both are gated by the same golden corpus (tests/contract/golden) — any
// divergence is a CI failure. Serializer: emits spec-conformant responses.
//
// Docs: docs/components/protocol.md v1.0.

#pragma once

#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

namespace sirah::eyes::core {

enum class Kind { Command, Response, Error, Ignored };

struct ParseResult {
  Kind kind = Kind::Ignored;
  std::string name;      // verb or response token (uppercase)
  std::vector<std::string> args;
  int code = 0;          // error code for Kind::Error

  std::string verdict() const;
};

// Parses one line payload (WITHOUT the trailing '\n'). Spec 4-9.
ParseResult parse_line(std::string_view line);

// Serializers (spec 7): exact response text.
inline constexpr char kReadyLine[] = "READY 1";
inline constexpr char kOkLine[] = "OK";
std::string format_state(float x, float y, int blink_flag);
std::string format_err(int code);

}  // namespace sirah::eyes::core