//go:build !silero

package voice

import (
	"math"
	"sort"
)

func defaultVoiceDetector(config VADConfig) (VoiceDetector, error) {
	return NewAdaptiveEnergyDetector(config), nil
}

// Energy VAD keeps the default build independent from native WebRTC headers.
type EnergyDetector struct{}

func (EnergyDetector) Process(frame []byte) Detection {
	if len(frame) == 0 {
		return Detection{}
	}
	var sum int64
	for i := 0; i+1 < len(frame); i += 2 {
		v := int64(int16(uint16(frame[i]) | uint16(frame[i+1])<<8))
		sum += v * v
	}
	if len(frame) < 2 {
		return Detection{}
	}
	meanSquare := float64(sum) / float64(len(frame)/2)
	return Detection{Speech: meanSquare > 900000}
}
func (EnergyDetector) Reset()       {}
func (EnergyDetector) Name() string { return "energy" }
func (EnergyDetector) Close() error { return nil }

type AdaptiveEnergyDetector struct {
	calibrationFrames   int
	startMultiple       float64
	endMultiple         float64
	minStartRMS         float64
	minEndRMS           float64
	frames              int
	rmsValues           []float64
	startThreshold      float64
	endThreshold        float64
	noiseFloor          float64
	silenceFrames       int
	stableSilenceFrames int
	active              bool
	onCalibration       func(CalibrationStats)
}

func NewAdaptiveEnergyDetector(config VADConfig) *AdaptiveEnergyDetector {
	calibrationFrames := int(config.Calibration / vadFrameDuration)
	if calibrationFrames < 1 {
		calibrationFrames = 1
	}
	return &AdaptiveEnergyDetector{calibrationFrames: calibrationFrames, startMultiple: config.StartMultiple, endMultiple: config.EndMultiple, minStartRMS: config.MinStartRMS, minEndRMS: config.MinEndRMS, rmsValues: make([]float64, 0, calibrationFrames), onCalibration: config.OnCalibration}
}

func (d *AdaptiveEnergyDetector) BeginUtterance(onCalibration func(CalibrationStats)) {
	d.active = false
	d.silenceFrames = 0
	d.onCalibration = onCalibration
}

func (d *AdaptiveEnergyDetector) EndUtterance() {
	d.active = false
	d.silenceFrames = 0
}

func (d *AdaptiveEnergyDetector) Process(frame []byte) Detection {
	rms := frameRMS(frame)
	if d.frames < d.calibrationFrames {
		d.frames++
		d.rmsValues = append(d.rmsValues, rms)
		if d.frames == d.calibrationFrames {
			stats := calibrationStats(d.rmsValues)
			d.setNoiseFloor(stats.P90)
			if d.onCalibration != nil {
				d.onCalibration(stats)
			}
		}
		return Detection{Probability: 0}
	}
	threshold := d.startThreshold
	if d.active {
		threshold = d.endThreshold
	}
	speech := rms >= threshold
	if speech {
		d.active = true
		d.silenceFrames = 0
	} else {
		d.silenceFrames++
		if d.active && rms < d.endThreshold {
			d.active = false
		}
		if !d.active && d.silenceFrames >= d.stableSilenceFrames && rms <= d.startThreshold {
			d.updateNoiseFloor(rms)
		}
	}
	probability := 0.0
	if d.startThreshold > d.endThreshold {
		probability = (rms - d.endThreshold) / (d.startThreshold - d.endThreshold)
		if probability < 0 {
			probability = 0
		}
		if probability > 1 {
			probability = 1
		}
	}
	return Detection{Speech: speech, Probability: float32(probability)}
}

func (d *AdaptiveEnergyDetector) Reset() {
	d.frames = 0
	d.rmsValues = d.rmsValues[:0]
	d.startThreshold = 0
	d.endThreshold = 0
	d.active = false
	d.noiseFloor = 0
	d.silenceFrames = 0
}
func (d *AdaptiveEnergyDetector) Name() string { return "energy_adaptive" }
func (d *AdaptiveEnergyDetector) Close() error { return nil }

func (d *AdaptiveEnergyDetector) setNoiseFloor(noiseFloor float64) {
	d.noiseFloor = noiseFloor
	d.startThreshold = maxFloat(noiseFloor*d.startMultiple, d.minStartRMS)
	d.endThreshold = maxFloat(noiseFloor*d.endMultiple, d.minEndRMS)
	if d.endThreshold >= d.startThreshold {
		d.endThreshold = d.startThreshold * 0.7
	}
	d.stableSilenceFrames = 20
}

func (d *AdaptiveEnergyDetector) updateNoiseFloor(rms float64) {
	if d.noiseFloor <= 0 || rms > d.startThreshold {
		return
	}
	candidate := d.noiseFloor*0.995 + rms*0.005
	maxStep := d.noiseFloor * 0.02
	if candidate > d.noiseFloor+maxStep {
		candidate = d.noiseFloor + maxStep
	}
	if candidate < d.noiseFloor-maxStep {
		candidate = d.noiseFloor - maxStep
	}
	d.setNoiseFloor(candidate)
}

func frameRMS(frame []byte) float64 {
	if len(frame) < 2 {
		return 0
	}
	var sum int64
	for i := 0; i+1 < len(frame); i += 2 {
		value := int64(int16(uint16(frame[i]) | uint16(frame[i+1])<<8))
		sum += value * value
	}
	return sqrtFloat(float64(sum) / float64(len(frame)/2))
}

func calibrationStats(values []float64) CalibrationStats {
	if len(values) == 0 {
		return CalibrationStats{}
	}
	sorted := append([]float64(nil), values...)
	sort.Float64s(sorted)
	return CalibrationStats{Min: sorted[0], Median: quantile(sorted, 0.5), P90: quantile(sorted, 0.9), P99: quantile(sorted, 0.99), Max: sorted[len(sorted)-1]}
}

func quantile(sorted []float64, q float64) float64 {
	index := int(float64(len(sorted)-1) * q)
	return sorted[index]
}

func maxFloat(value, minimum float64) float64 {
	if value < minimum {
		return minimum
	}
	return value
}

func sqrtFloat(value float64) float64 {
	return math.Sqrt(value)
}
