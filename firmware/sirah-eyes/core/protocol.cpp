// Shared wire-protocol layer — implementation. Spec protocol.md v1.0,
// mirrored by the Python parser; both gated on the same golden corpus.

#include "core/protocol.h"

#include <cctype>
#include <cstdio>
#include <cstdlib>

namespace sirah::eyes::core {

namespace {

// spec 4: 64 bytes per line INCLUDING the '\n'.
constexpr size_t kMaxPayloadBytes = 63;

// spec 6.2 / 7.1 token arity table.
int command_arity(std::string_view tok) {
  if (tok == "TARGET") return 2;
  if (tok == "CENTER" || tok == "BLINK" || tok == "HEARTBEAT" || tok == "STATUS") return 0;
  return -1;
}
int response_arity(std::string_view tok) {
  if (tok == "READY") return 1;
  if (tok == "OK") return 0;
  if (tok == "STATE") return 3;
  if (tok == "ERR") return 1;
  return -1;
}

// spec 5: "num" syntax (mirror of the Python regex):
//   -?(0|[1-9][0-9]*)(\.[0-9]{1,3})?
bool is_num(std::string_view s) {
  size_t i = 0;
  if (i < s.size() && s[i] == '-') ++i;
  if (i >= s.size()) return false;
  if (s[i] == '0') {
    ++i;
  } else if (s[i] >= '1' && s[i] <= '9') {
    while (i < s.size() && std::isdigit(static_cast<unsigned char>(s[i]))) ++i;
  } else {
    return false;
  }
  if (i < s.size() && s[i] == '.') {
    ++i;
    int digits = 0;
    while (i < s.size() && std::isdigit(static_cast<unsigned char>(s[i]))) {
      ++i;
      if (++digits > 3) return false;
    }
    if (digits == 0) return false;
  }
  return i == s.size();
}

bool in_range(std::string_view s) {
  double v = std::strtod(std::string(s).c_str(), nullptr);
  return v >= -1.0 && v <= 1.0;
}

bool printable(std::string_view s) {
  for (unsigned char c : s) {
    if (c < 0x20 || c > 0x7E) return false;
  }
  return true;
}

}  // namespace

std::string ParseResult::verdict() const {
  switch (kind) {
    case Kind::Command: return "CMD:" + name;
    case Kind::Response: return "RESP:" + name;
    case Kind::Error: return "ERR:" + std::to_string(code);
    case Kind::Ignored: return "IGNORE";
  }
  return "?";
}

ParseResult parse_line(std::string_view line) {
  if (line.size() > kMaxPayloadBytes) return {Kind::Error, {}, {}, 2};
  if (!printable(line)) return {Kind::Error, {}, {}, 2};
  if (line.empty()) return {Kind::Ignored, {}, {}, 0};

  std::vector<std::string> tokens;
  std::string cur;
  for (char c : line) {
    if (c == ' ') {
      tokens.push_back(cur);
      cur.clear();
    } else {
      cur.push_back(c);
    }
  }
  tokens.push_back(cur);

  const std::string& name = tokens.front();
  int cmd_arity = command_arity(name);
  int resp_arity = response_arity(name);
  if (cmd_arity < 0 && resp_arity < 0) return {Kind::Error, {}, {}, 1};

  const bool is_cmd = cmd_arity >= 0;
  const int arity = is_cmd ? cmd_arity : resp_arity;
  std::vector<std::string> args(tokens.begin() + 1, tokens.end());
  if (static_cast<int>(args.size()) != arity) return {Kind::Error, {}, {}, 2};

  if (name == "TARGET") {
    for (const auto& a : args) {
      if (!is_num(a)) return {Kind::Error, {}, {}, 2};
      if (!in_range(a)) return {Kind::Error, {}, {}, 3};
    }
    return {Kind::Command, name, args, 0};
  }
  if (is_cmd) return {Kind::Command, name, args, 0};

  if (name == "READY") {
    if (args[0] != "1") return {Kind::Error, {}, {}, 2};
    return {Kind::Response, name, args, 0};
  }
  if (name == "STATE") {
    const std::string& x = args[0];
    const std::string& y = args[1];
    const std::string& blink = args[2];
    if (!is_num(x) || !is_num(y)) return {Kind::Error, {}, {}, 2};
    if (!in_range(x) || !in_range(y)) return {Kind::Error, {}, {}, 3};
    if (blink != "0" && blink != "1") return {Kind::Error, {}, {}, 2};
    return {Kind::Response, name, args, 0};
  }
  if (name == "ERR") {
    const std::string& c = args[0];
    if (c != "1" && c != "2" && c != "3" && c != "5") return {Kind::Error, {}, {}, 2};
    return {Kind::Response, name, args, 0};
  }
  if (name == "OK") return {Kind::Response, name, args, 0};
  return {Kind::Error, {}, {}, 2};  // unreachable
}

std::string format_state(float x, float y, int blink_flag) {
  char buf[40];
  // Avoid the "-0.000" artifact: clamp tiny negatives to zero.
  if (x > -0.0005F && x < 0.0F) x = 0.0F;
  if (y > -0.0005F && y < 0.0F) y = 0.0F;
  std::snprintf(buf, sizeof(buf), "STATE %.3f %.3f %d", (double)x, (double)y,
                blink_flag ? 1 : 0);
  return buf;
}

std::string format_err(int code) { return "ERR " + std::to_string(code); }

}  // namespace sirah::eyes::core