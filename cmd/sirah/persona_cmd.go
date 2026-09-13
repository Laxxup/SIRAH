package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/Laxxup/SIRAH/internal/sirah"
)

func runPersonaCommand(args []string) int {
	if len(args) == 0 {
		printPersonaUsage()
		return 2
	}

	switch args[0] {
	case "inspect":
		if len(args) < 2 {
			fmt.Fprintln(os.Stderr, "Usage: sirah persona inspect <file>")
			return 2
		}
		return runPersonaInspect(args[1])
	case "import":
		return runPersonaImport(args[1:])
	case "list":
		return runPersonaList()
	case "-h", "--help", "help":
		printPersonaUsage()
		return 0
	default:
		fmt.Fprintf(os.Stderr, "Unknown persona subcommand: %s\n", args[0])
		printPersonaUsage()
		return 2
	}
}

func printPersonaUsage() {
	fmt.Fprint(os.Stderr, `Usage: sirah persona <command> [options]

Commands:
  inspect <file>          Inspect a Character Card and show mapped persona
  import <file>           Import a Character Card as a native persona profile
    --profile <name>      Target profile name (required)
    --force               Overwrite existing profile
  list                    List available persona profiles
`)
}

func runPersonaInspect(filePath string) int {
	data, err := os.ReadFile(filePath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error reading file: %v\n", err)
		return 1
	}

	p, result, err := sirah.ParseAndMap(data)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error parsing card: %v\n", err)
		return 1
	}

	fmt.Printf("Detected format: %v\n", result.Format)
	if len(result.Errors) > 0 {
		fmt.Println("Errors:")
		for _, e := range result.Errors {
			fmt.Printf("  - %s\n", e)
		}
	}
	if len(result.Blocked) > 0 {
		fmt.Println("Blocked fields (security):")
		for _, f := range result.Blocked {
			fmt.Printf("  - %s\n", f)
		}
	}
	if len(result.Ignored) > 0 {
		fmt.Println("Ignored fields:")
		for _, f := range result.Ignored {
			fmt.Printf("  - %s\n", f)
		}
	}
	if len(result.Warnings) > 0 {
		fmt.Println("Warnings:")
		for _, w := range result.Warnings {
			fmt.Printf("  - %s\n", w)
		}
	}

	out, err := json.MarshalIndent(p, "", "  ")
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error marshaling persona: %v\n", err)
		return 1
	}
	fmt.Println("Mapped persona:")
	fmt.Println(string(out))
	return 0
}

func runPersonaImport(args []string) int {
	var filePath, profileName string
	var force bool

	for i := 0; i < len(args); i++ {
		switch args[i] {
		case "--profile":
			if i+1 >= len(args) {
				fmt.Fprintln(os.Stderr, "--profile requires a value")
				return 2
			}
			profileName = args[i+1]
			i++
		case "--force":
			force = true
		default:
			if filePath == "" {
				filePath = args[i]
			} else {
				fmt.Fprintf(os.Stderr, "Unexpected argument: %s\n", args[i])
				return 2
			}
		}
	}

	if filePath == "" {
		fmt.Fprintln(os.Stderr, "Usage: sirah persona import <file> --profile <name> [--force]")
		return 2
	}
	if profileName == "" {
		fmt.Fprintln(os.Stderr, "--profile is required")
		return 2
	}
	if !sirah.IsValidProfileName(profileName) {
		fmt.Fprintf(os.Stderr, "Invalid profile name: %q\n", profileName)
		return 2
	}

	data, err := os.ReadFile(filePath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error reading file: %v\n", err)
		return 1
	}

	p, result, err := sirah.ParseAndMap(data)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error parsing card: %v\n", err)
		return 1
	}
	if len(result.Errors) > 0 {
		fmt.Fprintln(os.Stderr, "Card contains errors:")
		for _, e := range result.Errors {
			fmt.Fprintf(os.Stderr, "  - %s\n", e)
		}
		return 1
	}

	// Show warnings
	if len(result.Blocked) > 0 {
		fmt.Println("Blocked fields (security):")
		for _, f := range result.Blocked {
			fmt.Printf("  - %s\n", f)
		}
	}
	if len(result.Ignored) > 0 {
		fmt.Println("Ignored fields:")
		for _, f := range result.Ignored {
			fmt.Printf("  - %s\n", f)
		}
	}
	if len(result.Warnings) > 0 {
		fmt.Println("Warnings:")
		for _, w := range result.Warnings {
			fmt.Printf("  - %s\n", w)
		}
	}

	profilesDir := getProfilesDir()
	outPath := filepath.Join(profilesDir, profileName+".persona.json")

	if _, err := os.Stat(outPath); err == nil && !force {
		fmt.Fprintf(os.Stderr, "Profile %q already exists. Use --force to overwrite.\n", profileName)
		return 1
	}

	if err := os.MkdirAll(profilesDir, 0755); err != nil {
		fmt.Fprintf(os.Stderr, "Error creating profiles directory: %v\n", err)
		return 1
	}

	outData, err := json.MarshalIndent(p, "", "  ")
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error marshaling persona: %v\n", err)
		return 1
	}

	// Atomic write: tmp + rename
	tmpPath := outPath + ".tmp"
	if err := os.WriteFile(tmpPath, outData, 0644); err != nil {
		fmt.Fprintf(os.Stderr, "Error writing file: %v\n", err)
		return 1
	}
	if err := os.Rename(tmpPath, outPath); err != nil {
		os.Remove(tmpPath)
		fmt.Fprintf(os.Stderr, "Error renaming file: %v\n", err)
		return 1
	}

	fmt.Printf("Imported %q as profile %q -> %s\n", filePath, profileName, outPath)
	return 0
}

func runPersonaList() int {
	profilesDir := getProfilesDir()
	entries, err := os.ReadDir(profilesDir)
	if err != nil {
		if os.IsNotExist(err) {
			fmt.Println("No profiles directory found.")
			return 0
		}
		fmt.Fprintf(os.Stderr, "Error reading profiles directory: %v\n", err)
		return 1
	}

	fmt.Println("Available profiles:")
	found := false
	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		name := entry.Name()
		if strings.HasSuffix(name, ".persona.json") {
			fmt.Printf("  - %s\n", strings.TrimSuffix(name, ".persona.json"))
			found = true
		} else if strings.HasSuffix(name, ".json") {
			// Raw character cards are also listed but marked
			fmt.Printf("  - %s (raw character card)\n", strings.TrimSuffix(name, ".json"))
			found = true
		}
	}
	if !found {
		fmt.Println("  (none)")
	}
	return 0
}

var profilesDir = "personas"

func getProfilesDir() string {
	return profilesDir
}
