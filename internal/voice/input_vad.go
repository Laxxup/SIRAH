package voice

import "time"

type Detection struct {
	Speech      bool
	Probability float32
}

type VADResult struct {
	Audio          []byte
	EndReason      EndReason
	Valid          bool
	WaitForSpeech  time.Duration
	SpeechDuration time.Duration
	EndSilence     time.Duration
	TotalDuration  time.Duration
	CaptureStart   time.Time
	FirstSpeech    time.Time
	UserEnd        time.Time
	ClosedAt       time.Time
	SampleRate     int
}

type CalibrationStats struct {
	Min    float64
	Median float64
	P90    float64
	P99    float64
	Max    float64
}

type AudioPreprocessor interface {
	Process([]byte) ([]byte, error)
	InputRate() int
	OutputRate() int
	Close() error
	Name() string
}

type PassthroughPreprocessor struct{}

func (PassthroughPreprocessor) Process(frame []byte) ([]byte, error) { return frame, nil }
func (PassthroughPreprocessor) InputRate() int                       { return 16000 }
func (PassthroughPreprocessor) OutputRate() int                      { return 16000 }
func (PassthroughPreprocessor) Close() error                         { return nil }
func (PassthroughPreprocessor) Name() string                         { return "passthrough" }

// VoiceDetector classifies signed 16-bit little-endian, mono, 16 kHz PCM frames.
type VoiceDetector interface {
	Process(frame []byte) Detection
	Reset()
	Name() string
	Close() error
}

type VoiceDetectorFactory func(config VADConfig) (VoiceDetector, error)
