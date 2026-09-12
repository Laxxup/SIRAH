package voice

import (
	"bytes"
	"context"
	"encoding/binary"
	"fmt"
	"io"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"time"
)

type Recorder struct {
	Command      string
	Device       string
	CaptureRate  int
	FallbackRate int
	Preprocessor AudioPreprocessor
	Detector     VoiceDetectorFactory
	detector     VoiceDetector
	processed    []byte
}

const DefaultInputDevice = "plughw:CARD=PCH,DEV=0"

type VADConfig struct {
	Silence       time.Duration
	Maximum       time.Duration
	PreBuffer     time.Duration
	MinimumSpeech time.Duration
	DetectorName  string
	StartFrames   int
	Cooldown      time.Duration
	Debug         bool
	Logf          func(string, ...any)
	OnResult      func(VADResult)
	OnCalibration func(CalibrationStats)
	Calibration   time.Duration
	StartMultiple float64
	EndMultiple   float64
	MinStartRMS   float64
	MinEndRMS     float64
}

type EndReason string

const (
	EndReasonNone        EndReason = ""
	EndReasonSilence     EndReason = "Silence"
	EndReasonMaxDuration EndReason = "MaxDuration"
)

type VADState string

const (
	StateListening VADState = "LISTENING"
	StateRecording VADState = "RECORDING"
	StatePlaying   VADState = "PLAYING"
)

func DefaultVADConfig() VADConfig {
	return VADConfig{
		StartFrames:   3,
		Silence:       400 * time.Millisecond,
		Maximum:       10 * time.Second,
		PreBuffer:     300 * time.Millisecond,
		MinimumSpeech: 100 * time.Millisecond,
		DetectorName:  "energy",
		Cooldown:      200 * time.Millisecond,
		Calibration:   500 * time.Millisecond,
		StartMultiple: 1.6,
		EndMultiple:   1.2,
		MinStartRMS:   1200,
		MinEndRMS:     600,
	}
}

func NewRecorder(command, device string) Recorder {
	if command == "" {
		command = "arecord"
	}
	return Recorder{Command: command, Device: device, CaptureRate: 16000, Preprocessor: PassthroughPreprocessor{}, Detector: defaultVoiceDetector}
}

func NewRecorderWithMode(command, device, mode string) (Recorder, error) {
	if command == "" {
		command = "arecord"
	}
	var preprocessor AudioPreprocessor
	switch strings.ToLower(strings.TrimSpace(mode)) {
	case "", "raw":
		preprocessor = PassthroughPreprocessor{}
	case "rnnoise":
		// Experimental optional STT preprocessor; RAW remains the product path.
		var err error
		preprocessor, err = NewRNNoisePreprocessor()
		if err != nil {
			return Recorder{}, fmt.Errorf("create STT preprocessor %q: %w", mode, err)
		}
	default:
		return Recorder{}, fmt.Errorf("unsupported STT_PREPROCESSOR %q", mode)
	}
	return Recorder{Command: command, Device: device, CaptureRate: preprocessor.InputRate(), FallbackRate: 0, Preprocessor: preprocessor, Detector: defaultVoiceDetector}, nil
}

func (r *Recorder) Close() error {
	if r.Preprocessor == nil {
		return nil
	}
	return r.Preprocessor.Close()
}

func (r *Recorder) RecordUtterance(ctx context.Context, config VADConfig) ([]byte, EndReason, error) {
	rate := r.CaptureRate
	if rate <= 0 {
		rate = 16000
	}
	audio, reason, err := r.recordRate(ctx, config, rate)
	if err == nil || ctx.Err() != nil || r.FallbackRate <= 0 || rate == r.FallbackRate || !captureRateMayBeUnsupported(err) {
		return audio, reason, err
	}
	return r.recordRate(ctx, config, r.FallbackRate)
}

func captureRateMayBeUnsupported(err error) bool {
	if err == nil {
		return false
	}
	message := err.Error()
	return strings.Contains(message, "start microphone") || strings.Contains(message, "microphone stream ended")
}

func (r *Recorder) recordRate(ctx context.Context, config VADConfig, rate int) ([]byte, EndReason, error) {
	if config.StartFrames < 1 || config.Silence <= 0 || config.Maximum <= 0 || config.PreBuffer < 0 || config.MinimumSpeech < 0 {
		return nil, EndReasonNone, fmt.Errorf("invalid VAD configuration")
	}
	captureStart := time.Now()
	frameBytes := frameBytesForRate(rate)
	args := []string{"-f", "S16_LE", "-r", fmt.Sprint(rate), "-c", "1", "-t", "raw"}
	if r.Device != "" {
		args = append([]string{"-D", r.Device}, args...)
	}
	cmd := exec.CommandContext(ctx, r.Command, args...)
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return nil, EndReasonNone, fmt.Errorf("microphone stdout: %w", err)
	}
	if err := cmd.Start(); err != nil {
		return nil, EndReasonNone, fmt.Errorf("start microphone at %d Hz: %w", rate, err)
	}
	finish := func() {
		if cmd.Process != nil {
			_ = cmd.Process.Signal(os.Interrupt)
		}
		_ = stdout.Close()
		wait := make(chan error, 1)
		go func() { wait <- cmd.Wait() }()
		select {
		case <-wait:
		case <-time.After(2 * time.Second):
			_ = cmd.Process.Kill()
			<-wait
		}
	}
	preprocessor := r.Preprocessor
	if preprocessor == nil {
		preprocessor = PassthroughPreprocessor{}
	}
	detector := r.detector
	persistent := detector != nil
	if detector == nil {
		factory := r.Detector
		if factory == nil {
			factory = defaultVoiceDetector
		}
		var err error
		detector, err = factory(config)
		if err != nil {
			finish()
			return nil, EndReasonNone, err
		}
		if _, ok := detector.(*AdaptiveEnergyDetector); ok {
			r.detector = detector
			persistent = true
		}
	}
	if !persistent {
		defer detector.Close()
	}
	if adaptive, ok := detector.(*AdaptiveEnergyDetector); ok {
		adaptive.BeginUtterance(config.OnCalibration)
	}
	if config.Debug && config.Logf != nil {
		config.Logf("AudioPreprocessor: %s", preprocessor.Name())
		config.Logf("VoiceDetector: %s", detector.Name())
	}
	chunk := make([]byte, frameBytes)
	preBuffer := make([][]byte, 0, preBufferFrames(config.PreBuffer))
	var pcm bytes.Buffer
	var waitForSpeech, speechDuration, silenceDuration, totalDuration time.Duration
	var firstSpeech, lastSpeech time.Time
	activeFrames := 0
	started := false
	const frameDuration = 10 * time.Millisecond
	for {
		read, readErr := io.ReadFull(stdout, chunk)
		if read == frameBytes {
			frame, processErr := preprocessor.Process(chunk[:read])
			if processErr != nil {
				finish()
				return nil, EndReasonNone, processErr
			}
			r.processed = append(r.processed, frame...)
			vadFrameBytes := frameBytesForRate(preprocessor.OutputRate())
			for len(r.processed) >= vadFrameBytes {
				vadFrame := r.processed[:vadFrameBytes]
				r.processed = r.processed[vadFrameBytes:]
				voice := detector.Process(vadFrame).Speech
				totalDuration += frameDuration
				frameEnd := captureStart.Add(totalDuration)
				if !started {
					preBuffer = append(preBuffer, append([]byte(nil), vadFrame...))
					keepPreBuffer(&preBuffer, config.PreBuffer)
					if voice {
						activeFrames++
						if firstSpeech.IsZero() {
							firstSpeech = captureStart.Add(totalDuration - frameDuration)
						}
					} else {
						activeFrames = 0
					}
					if activeFrames < config.StartFrames {
						if totalDuration >= config.Maximum {
							finish()
							if adaptive, ok := detector.(*AdaptiveEnergyDetector); ok {
								adaptive.EndUtterance()
							}
							return nil, EndReasonNone, fmt.Errorf("no speech detected before maximum duration")
						}
						continue
					}
					started = true
					waitForSpeech = totalDuration
					speechDuration = time.Duration(activeFrames) * frameDuration
					lastSpeech = frameEnd
					if config.Debug && config.Logf != nil {
						config.Logf("Voice debug: speech started")
					}
					for _, buffered := range preBuffer {
						pcm.Write(buffered)
					}
					preBuffer = nil
				} else {
					pcm.Write(vadFrame)
					if voice {
						speechDuration += frameDuration
						silenceDuration = 0
						lastSpeech = frameEnd
					} else {
						silenceDuration += frameDuration
					}
				}
				if started && (silenceDuration >= config.Silence || totalDuration >= config.Maximum) {
					reason := EndReasonSilence
					if totalDuration >= config.Maximum && silenceDuration < config.Silence {
						reason = EndReasonMaxDuration
					}
					closedAt := time.Now()
					result := VADResult{Audio: wavBytes(pcm.Bytes(), preprocessor.OutputRate()), EndReason: reason, Valid: speechDuration >= config.MinimumSpeech, WaitForSpeech: waitForSpeech, SpeechDuration: speechDuration, EndSilence: silenceDuration, TotalDuration: totalDuration, CaptureStart: captureStart, FirstSpeech: firstSpeech, UserEnd: lastSpeech, ClosedAt: closedAt, SampleRate: preprocessor.OutputRate()}
					if config.OnResult != nil {
						config.OnResult(result)
					}
					finish()
					if adaptive, ok := detector.(*AdaptiveEnergyDetector); ok {
						adaptive.EndUtterance()
					}
					if !result.Valid {
						return nil, result.EndReason, fmt.Errorf("no speech detected")
					}
					return result.Audio, result.EndReason, nil
				}
			}
		}
		if readErr != nil {
			finish()
			if ctx.Err() != nil {
				return nil, EndReasonNone, ctx.Err()
			}
			return nil, EndReasonNone, fmt.Errorf("microphone stream ended: %w", readErr)
		}
		select {
		case <-ctx.Done():
			finish()
			return nil, EndReasonNone, ctx.Err()
		default:
		}
	}
}

func wavBytes(pcm []byte, sampleRate int) []byte {
	var header bytes.Buffer
	header.WriteString("RIFF")
	_ = binary.Write(&header, binary.LittleEndian, uint32(36+len(pcm)))
	header.WriteString("WAVEfmt ")
	_ = binary.Write(&header, binary.LittleEndian, uint32(16))
	_ = binary.Write(&header, binary.LittleEndian, uint16(1))
	_ = binary.Write(&header, binary.LittleEndian, uint16(1))
	_ = binary.Write(&header, binary.LittleEndian, uint32(sampleRate))
	_ = binary.Write(&header, binary.LittleEndian, uint32(sampleRate*2))
	_ = binary.Write(&header, binary.LittleEndian, uint16(2))
	_ = binary.Write(&header, binary.LittleEndian, uint16(16))
	header.WriteString("data")
	_ = binary.Write(&header, binary.LittleEndian, uint32(len(pcm)))
	header.Write(pcm)
	return header.Bytes()
}

func VADConfigFromEnv(getenv func(string) string) VADConfig {
	c := DefaultVADConfig()
	c.StartFrames = envInt(getenv, "VOICE_START_FRAMES", c.StartFrames)
	c.Silence = envDuration(getenv, "VOICE_SILENCE_MS", c.Silence)
	c.Maximum = envDuration(getenv, "VOICE_MAX_TURN_MS", c.Maximum)
	c.PreBuffer = envDuration(getenv, "VOICE_PREBUFFER_MS", c.PreBuffer)
	c.MinimumSpeech = envDuration(getenv, "VOICE_MIN_SPEECH_MS", c.MinimumSpeech)
	c.Calibration = envDuration(getenv, "VOICE_NOISE_CALIBRATION_MS", c.Calibration)
	c.StartMultiple = envFloat(getenv, "VOICE_START_MULTIPLE", c.StartMultiple)
	c.EndMultiple = envFloat(getenv, "VOICE_END_MULTIPLE", c.EndMultiple)
	c.MinStartRMS = envFloat(getenv, "VOICE_MIN_START_RMS", c.MinStartRMS)
	c.MinEndRMS = envFloat(getenv, "VOICE_MIN_END_RMS", c.MinEndRMS)
	c.DetectorName = "energy"
	return c
}

func envInt(getenv func(string) string, name string, fallback int) int {
	value, err := strconv.Atoi(getenv(name))
	if err != nil || value <= 0 {
		return fallback
	}
	return value
}

func envFloat(getenv func(string) string, name string, fallback float64) float64 {
	value, err := strconv.ParseFloat(getenv(name), 64)
	if err != nil || value <= 0 {
		return fallback
	}
	return value
}

func envDuration(getenv func(string) string, name string, fallback time.Duration) time.Duration {
	value, err := strconv.Atoi(getenv(name))
	if err != nil || value <= 0 {
		return fallback
	}
	return time.Duration(value) * time.Millisecond
}

const vadFrameDuration = 10 * time.Millisecond

func preBufferFrames(duration time.Duration) int {
	if duration <= 0 {
		return 0
	}
	frames := int(duration / vadFrameDuration)
	if duration%vadFrameDuration != 0 {
		frames++
	}
	return frames
}

func keepPreBuffer(buffer *[][]byte, duration time.Duration) {
	limit := preBufferFrames(duration)
	if limit == 0 {
		*buffer = (*buffer)[:0]
		return
	}
	if len(*buffer) > limit {
		*buffer = (*buffer)[len(*buffer)-limit:]
	}
}

// RecordUntil is retained for the manual :voice mode.
func (r Recorder) RecordUntil(ctx context.Context, stop <-chan struct{}) ([]byte, error) {
	file, err := os.CreateTemp("", "agente-robotico-*.wav")
	if err != nil {
		return nil, err
	}
	path := file.Name()
	if err := file.Close(); err != nil {
		os.Remove(path)
		return nil, err
	}
	defer os.Remove(path)
	args := []string{"-f", "S16_LE", "-r", fmt.Sprint(audioSampleRate), "-c", "1", "-t", "wav", path}
	if r.Device != "" {
		args = append([]string{"-D", r.Device}, args...)
	}
	cmd := exec.CommandContext(ctx, r.Command, args...)
	if err := cmd.Start(); err != nil {
		return nil, fmt.Errorf("start microphone: %w", err)
	}
	done := make(chan error, 1)
	go func() {
		<-stop
		if cmd.Process != nil {
			_ = cmd.Process.Signal(os.Interrupt)
		}
		done <- cmd.Wait()
	}()
	select {
	case err := <-done:
		if err != nil && ctx.Err() != nil {
			return nil, ctx.Err()
		}
	case <-ctx.Done():
		_ = cmd.Process.Kill()
		_ = cmd.Wait()
		return nil, ctx.Err()
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read microphone recording: %w", err)
	}
	if len(data) == 0 {
		return nil, fmt.Errorf("microphone produced empty recording")
	}
	return data, nil
}
