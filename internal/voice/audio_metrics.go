package voice

import (
	"encoding/binary"
	"fmt"
	"math"
)

type AudioMetrics struct {
	SampleRate        int     `json:"sample_rate"`
	DurationMS        float64 `json:"duration_ms"`
	LeadingSilenceMS  float64 `json:"leading_silence_ms"`
	TrailingSilenceMS float64 `json:"trailing_silence_ms"`
	SpeechDurationMS  float64 `json:"speech_duration_ms"`
	Peak              int     `json:"peak"`
	RMS               float64 `json:"rms"`
	ClippedSamples    int     `json:"clipped_samples"`
	DCOffset          float64 `json:"dc_offset"`
	SilenceThreshold  int     `json:"silence_threshold"`
}

type WAVInfo struct {
	SampleRate    int
	Channels      int
	AudioFormat   int
	BitsPerSample int
	ByteRate      int
	BlockAlign    int
	Data          []byte
}

// InspectWAV validates the PCM layout produced by wavBytes and returns its payload.
func InspectWAV(wav []byte) (WAVInfo, error) {
	if len(wav) < 44 || string(wav[:4]) != "RIFF" || string(wav[8:12]) != "WAVE" {
		return WAVInfo{}, fmt.Errorf("invalid WAV RIFF/WAVE header")
	}
	if int(binary.LittleEndian.Uint32(wav[4:8])) != len(wav)-8 {
		return WAVInfo{}, fmt.Errorf("invalid RIFF size")
	}
	var info WAVInfo
	var fmtFound, dataFound bool
	for offset := 12; offset+8 <= len(wav); {
		id := string(wav[offset : offset+4])
		size := int(binary.LittleEndian.Uint32(wav[offset+4 : offset+8]))
		start := offset + 8
		end := start + size
		if end > len(wav) {
			return WAVInfo{}, fmt.Errorf("WAV chunk %q exceeds file", id)
		}
		switch id {
		case "fmt ":
			if size < 16 {
				return WAVInfo{}, fmt.Errorf("short fmt chunk")
			}
			info.AudioFormat = int(binary.LittleEndian.Uint16(wav[start : start+2]))
			info.Channels = int(binary.LittleEndian.Uint16(wav[start+2 : start+4]))
			info.SampleRate = int(binary.LittleEndian.Uint32(wav[start+4 : start+8]))
			info.ByteRate = int(binary.LittleEndian.Uint32(wav[start+8 : start+12]))
			info.BlockAlign = int(binary.LittleEndian.Uint16(wav[start+12 : start+14]))
			info.BitsPerSample = int(binary.LittleEndian.Uint16(wav[start+14 : start+16]))
			fmtFound = true
		case "data":
			info.Data = wav[start:end]
			dataFound = true
		}
		offset = end
		if size%2 != 0 {
			offset++
		}
	}
	if !fmtFound || !dataFound {
		return WAVInfo{}, fmt.Errorf("WAV missing fmt or data chunk")
	}
	if info.AudioFormat != 1 || info.Channels != 1 || info.BitsPerSample != 16 || info.BlockAlign != 2 || info.ByteRate != info.SampleRate*info.BlockAlign || len(info.Data)%info.BlockAlign != 0 {
		return WAVInfo{}, fmt.Errorf("WAV is not mono 16-bit PCM")
	}
	return info, nil
}

func MeasureWAV(wav []byte) (AudioMetrics, error) {
	info, err := InspectWAV(wav)
	if err != nil {
		return AudioMetrics{}, err
	}
	const silenceThreshold = 600
	samples := len(info.Data) / 2
	if samples == 0 {
		return AudioMetrics{SampleRate: info.SampleRate, SilenceThreshold: silenceThreshold}, nil
	}
	var sum, peak int64
	clipped := 0
	firstSound, lastSound := samples, -1
	for i := 0; i < samples; i++ {
		value := int64(int16(binary.LittleEndian.Uint16(info.Data[i*2 : i*2+2])))
		abs := value
		if abs < 0 {
			abs = -abs
		}
		if abs > peak {
			peak = abs
		}
		if abs == 32768 {
			clipped++
		}
		sum += value
		if abs > silenceThreshold {
			if firstSound == samples {
				firstSound = i
			}
			lastSound = i
		}
	}
	duration := float64(samples) * 1000 / float64(info.SampleRate)
	leading := float64(firstSound) * 1000 / float64(info.SampleRate)
	trailing := 0.0
	if lastSound >= 0 {
		trailing = float64(samples-1-lastSound) * 1000 / float64(info.SampleRate)
	} else {
		trailing = duration
	}
	speech := duration - leading - trailing
	if speech < 0 {
		speech = 0
	}
	return AudioMetrics{
		SampleRate:        info.SampleRate,
		DurationMS:        duration,
		LeadingSilenceMS:  leading,
		TrailingSilenceMS: trailing,
		SpeechDurationMS:  speech,
		Peak:              int(peak),
		RMS:               math.Sqrt(float64(sumSquares(info.Data)) / float64(samples)),
		ClippedSamples:    clipped,
		DCOffset:          float64(sum) / float64(samples),
		SilenceThreshold:  silenceThreshold,
	}, nil
}

func sumSquares(pcm []byte) int64 {
	var sum int64
	for i := 0; i+1 < len(pcm); i += 2 {
		value := int64(int16(binary.LittleEndian.Uint16(pcm[i : i+2])))
		sum += value * value
	}
	return sum
}
