//go:build !rnnoise

package voice

import "fmt"

func NewRNNoisePreprocessor() (AudioPreprocessor, error) {
	return nil, fmt.Errorf("RNNoise unavailable: build with -tags rnnoise")
}
