package main

import (
	"encoding/json"
	"fmt"
	"os"

	"github.com/Laxxup/SIRAH/internal/sirah"
)

func main() {
	p := sirah.BuiltInPersona()
	data, err := json.MarshalIndent(p, "", "  ")
	if err != nil {
		fmt.Fprintf(os.Stderr, "error: %v\n", err)
		os.Exit(1)
	}
	fmt.Println(string(data))
}
