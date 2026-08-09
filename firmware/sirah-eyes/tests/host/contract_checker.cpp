// Contract gate checker: consumes the golden corpus directory and reports
// a verdict for every case; exit code 0 iff all cases pass.
//
// Usage: contract_checker <golden-dir>
// Output: "i=<n> got=<verdict>" per case + "TOTAL <n> FAILED <k>".
//
// The Python test (tests/contract/test_parsers_contract.py) runs this
// binary and compares its verdict sequence with the Python parser.

#include <algorithm>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "protocol_parser.h"

namespace fs = std::filesystem;

std::string unescape(const std::string& token) {
  std::string out;
  for (size_t i = 0; i < token.size();) {
    if (i + 4 <= token.size() && token[i] == '\\' && token[i + 1] == 'x') {
      auto hex = [&](char c) -> int {
        if (c >= '0' && c <= '9') return c - '0';
        if (c >= 'a' && c <= 'f') return c - 'a' + 10;
        return c - 'A' + 10;
      };
      out.push_back(static_cast<char>((hex(token[i + 2]) << 4) | hex(token[i + 3])));
      i += 4;
    } else {
      out.push_back(token[i]);
      ++i;
    }
  }
  return out;
}

int main(int argc, char** argv) {
  if (argc != 2) {
    std::cerr << "usage: contract_checker <golden-dir>\n";
    return 2;
  }
  int total = 0;
  int failed = 0;
  std::vector<fs::path> files;
  for (const auto& entry : fs::directory_iterator(argv[1])) {
    if (entry.path().extension() == ".txt") files.push_back(entry.path());
  }
  std::sort(files.begin(), files.end());
  for (const auto& path : files) {
    std::ifstream in(path);
    std::string line;
    while (std::getline(in, line)) {
      if (line.empty()) continue;
      auto sep = line.find('|');
      if (sep == std::string::npos) {
        std::cerr << "malformed corpus line in " << path.filename() << "\n";
        return 2;
      }
      std::string raw = unescape(line.substr(0, sep));
      std::string expected = line.substr(sep + 1);
      std::string got = sirah::contract::parse_line(raw).verdict();
      ++total;
      std::cout << "i=" << (total - 1) << " got=" << got << "\n";
      if (got != expected) {
        ++failed;
        std::cout << "FAIL file=" << path.filename() << " expected=" << expected
                  << " got=" << got << "\n";
      }
    }
  }
  std::cout << "TOTAL " << total << " FAILED " << failed << "\n";
  return failed == 0 ? 0 : 1;
}