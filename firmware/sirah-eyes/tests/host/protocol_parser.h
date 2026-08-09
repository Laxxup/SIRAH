// Host-side reference parser for the PC<->ESP32 line protocol
// (docs/components/protocol.md v1.0). Mirrors the canonical Python
// parser (src/sirah/protocol/parse_line.py); the contract gate runs
// both over the same golden corpus and requires identical verdicts.
//
// Purposely pure C++17 with no Arduino / platform dependencies: the
// firmware port (Stage 4) reuses this logic verbatim in core/.

#pragma once

#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

namespace sirah::contract {

enum class Kind { Command, Response, Error, Ignored };

struct ParseResult {
  Kind kind = Kind::Ignored;
  std::string name;      // verb or response token (uppercase)
  std::vector<std::string> args;
  int code = 0;          // error code for Kind::Error

  std::string verdict() const;
};

// Parses one line payload (WITHOUT the trailing '\n').
// Spec 4, 5, 6, 7, 9.
ParseResult parse_line(std::string_view line);

}  // namespace sirah::contract