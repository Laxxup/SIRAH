package voice

import (
	"bytes"
	"context"
	"encoding/binary"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func pcmFrame(sample int16) []byte {
	frame := make([]byte, audioFrameBytes)
	for i := 0; i < len(frame); i += 2 {
		binary.LittleEndian.PutUint16(frame[i:i+2], uint16(sample))
	}
	return frame
}

func TestEnergyDetectorClassifiesSilenceAndVoice(t *testing.T) {
	detector := EnergyDetector{}
	if detector.Process(pcmFrame(0)).Speech {
		t.Fatal("silence classified as speech")
	}
	if !detector.Process(pcmFrame(2000)).Speech {
		t.Fatal("voice classified as silence")
	}
}

func TestEnergyDetectorHandlesExtremePCM(t *testing.T) {
	detector := EnergyDetector{}
	if !detector.Process(pcmFrame(-32768)).Speech {
		t.Fatal("extreme PCM classified as silence")
	}
	if !detector.Process(pcmFrame(32767)).Speech {
		t.Fatal("extreme PCM classified as silence")
	}
}

func TestAdaptiveEnergyDetectorUsesHysteresisAndCalibration(t *testing.T) {
	var calibration CalibrationStats
	config := DefaultVADConfig()
	config.Calibration = 30 * time.Millisecond
	config.StartMultiple = 1.5
	config.EndMultiple = 1.1
	config.MinStartRMS = 100
	config.MinEndRMS = 50
	config.OnCalibration = func(stats CalibrationStats) { calibration = stats }
	detector := NewAdaptiveEnergyDetector(config)
	for i := 0; i < 3; i++ {
		if detector.Process(pcmFrameAtRate(100, 16000)).Speech {
			t.Fatal("calibration frame classified as speech")
		}
	}
	if calibration.P90 == 0 || calibration.Max == 0 {
		t.Fatalf("calibration stats = %+v", calibration)
	}
	if detector.Process(pcmFrameAtRate(120, 16000)).Speech {
		t.Fatal("first below-threshold frame classified as speech")
	}
	if !detector.Process(pcmFrameAtRate(1000, 16000)).Speech {
		t.Fatal("voice frame classified as silence")
	}
	if !detector.Process(pcmFrameAtRate(700, 16000)).Speech {
		t.Fatal("hysteresis end threshold rejected active voice")
	}
	if detector.Process(pcmFrameAtRate(100, 16000)).Speech {
		t.Fatal("silence classified as speech")
	}
}

func TestAdaptiveEnergyDetectorDoesNotLearnSpeechAsNoise(t *testing.T) {
	config := DefaultVADConfig()
	config.Calibration = 30 * time.Millisecond
	config.StartMultiple = 1.5
	config.EndMultiple = 1.1
	config.MinStartRMS = 100
	config.MinEndRMS = 50
	detector := NewAdaptiveEnergyDetector(config)
	for i := 0; i < 3; i++ {
		detector.Process(pcmFrameAtRate(100, 16000))
	}
	initial := detector.startThreshold
	for i := 0; i < 10; i++ {
		if !detector.Process(pcmFrameAtRate(3000, 16000)).Speech {
			t.Fatal("speech burst classified as silence")
		}
	}
	if detector.startThreshold > initial*1.01 {
		t.Fatalf("speech raised start threshold from %.1f to %.1f", initial, detector.startThreshold)
	}
}

func pcmFrameAtRate(sample int16, rate int) []byte {
	frame := make([]byte, frameBytesForRate(rate))
	for i := 0; i < len(frame); i += 2 {
		binary.LittleEndian.PutUint16(frame[i:i+2], uint16(sample))
	}
	return frame
}

func TestPreBufferIsBounded(t *testing.T) {
	buffer := make([][]byte, 0)
	for i := 0; i < 100; i++ {
		buffer = append(buffer, []byte{byte(i)})
		keepPreBuffer(&buffer, 30*time.Millisecond)
	}
	if len(buffer) != 3 {
		t.Fatalf("buffer length = %d, want 3", len(buffer))
	}
	if !bytes.Equal(buffer[0], []byte{97}) {
		t.Fatalf("oldest retained frame = %v", buffer[0])
	}
}

type scriptedDetector struct{ frame int }

func (d *scriptedDetector) Process([]byte) Detection {
	d.frame++
	return Detection{Speech: d.frame >= 3 && d.frame <= 5}
}
func (*scriptedDetector) Reset()       {}
func (*scriptedDetector) Name() string { return "scripted" }
func (*scriptedDetector) Close() error { return nil }

func TestRecordUtteranceDetectsStartAndSilenceEnd(t *testing.T) {
	dir := t.TempDir()
	dataPath := filepath.Join(dir, "pcm")
	data := bytes.Repeat(pcmFrame(0), 100)
	if err := os.WriteFile(dataPath, data, 0o600); err != nil {
		t.Fatal(err)
	}
	commandPath := filepath.Join(dir, "capture.sh")
	command := "#!/bin/sh\ncat " + dataPath + "\n"
	if err := os.WriteFile(commandPath, []byte(command), 0o700); err != nil {
		t.Fatal(err)
	}
	recorder := NewRecorder(commandPath, "ignored")
	recorder.Detector = func(VADConfig) (VoiceDetector, error) { return &scriptedDetector{}, nil }
	audio, reason, err := recorder.RecordUtterance(context.Background(), VADConfig{StartFrames: 3, Silence: 20 * time.Millisecond, Maximum: time.Second, PreBuffer: 20 * time.Millisecond, MinimumSpeech: 10 * time.Millisecond, DetectorName: "energy"})
	if err != nil {
		t.Fatal(err)
	}
	if reason != EndReasonSilence {
		t.Fatalf("end reason = %q", reason)
	}
	if len(audio) <= 44 {
		t.Fatalf("audio length = %d, expected PCM payload", len(audio))
	}
}

func TestAdaptiveRecordUtteranceEndsAfterSilence(t *testing.T) {
	dir := t.TempDir()
	dataPath := filepath.Join(dir, "pcm")
	var data []byte
	for i := 0; i < 50; i++ {
		data = append(data, pcmFrameAtRate(100, 16000)...)
	}
	for i := 0; i < 20; i++ {
		data = append(data, pcmFrameAtRate(3000, 16000)...)
	}
	for i := 0; i < 40; i++ {
		data = append(data, pcmFrameAtRate(100, 16000)...)
	}
	if err := os.WriteFile(dataPath, data, 0o600); err != nil {
		t.Fatal(err)
	}
	commandPath := filepath.Join(dir, "capture.sh")
	command := "#!/bin/sh\ncat " + dataPath + "\n"
	if err := os.WriteFile(commandPath, []byte(command), 0o700); err != nil {
		t.Fatal(err)
	}
	config := DefaultVADConfig()
	config.Calibration = 500 * time.Millisecond
	config.Silence = 400 * time.Millisecond
	config.Maximum = 5 * time.Second
	var result VADResult
	config.OnResult = func(value VADResult) { result = value }
	recorder := NewRecorder(commandPath, "ignored")
	_, reason, err := recorder.RecordUtterance(context.Background(), config)
	if err != nil {
		t.Fatal(err)
	}
	if reason != EndReasonSilence {
		t.Fatalf("end reason = %q, want silence", reason)
	}
	if result.EndSilence != config.Silence {
		t.Fatalf("end silence = %s, want %s", result.EndSilence, config.Silence)
	}
	if result.TotalDuration >= config.Maximum {
		t.Fatalf("utterance reached maximum: %s", result.TotalDuration)
	}
}

func TestAdaptiveDetectorCalibratesOnceAcrossUtterances(t *testing.T) {
	dir := t.TempDir()
	dataPath := filepath.Join(dir, "pcm")
	var data []byte
	for i := 0; i < 3; i++ {
		data = append(data, pcmFrameAtRate(100, 16000)...)
	}
	for i := 0; i < 3; i++ {
		data = append(data, pcmFrameAtRate(3000, 16000)...)
	}
	for i := 0; i < 4; i++ {
		data = append(data, pcmFrameAtRate(100, 16000)...)
	}
	dataPathScript := filepath.Join(dir, "capture.sh")
	if err := os.WriteFile(dataPath, data, 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(dataPathScript, []byte("#!/bin/sh\ncat "+dataPath+"\n"), 0o700); err != nil {
		t.Fatal(err)
	}
	config := DefaultVADConfig()
	config.Calibration = 30 * time.Millisecond
	config.Silence = 20 * time.Millisecond
	config.Maximum = time.Second
	config.MinimumSpeech = 10 * time.Millisecond
	calibrations := 0
	config.OnCalibration = func(CalibrationStats) { calibrations++ }
	recorder := NewRecorder(dataPathScript, "ignored")
	for i := 0; i < 2; i++ {
		if _, _, err := recorder.RecordUtterance(context.Background(), config); err != nil {
			t.Fatalf("utterance %d: %v", i+1, err)
		}
	}
	if calibrations != 1 {
		t.Fatalf("calibrations = %d, want one persistent calibration", calibrations)
	}
}
