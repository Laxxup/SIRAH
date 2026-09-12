// Package vision convierte frames en observaciones; no decide acciones.
package vision

import (
	"context"
	"sync"
	"time"
)

const maxDetections = 128

func retryRead(read func() error, attempts int, delay time.Duration) error {
	if attempts < 1 {
		attempts = 1
	}
	var err error
	for attempt := 0; attempt < attempts; attempt++ {
		if err = read(); err == nil {
			return nil
		}
		if attempt+1 < attempts && delay > 0 {
			time.Sleep(delay)
		}
	}
	return err
}

// Target es una posición normalizada en el frame, normalmente en [-1, 1].
type Target struct {
	X float64
	Y float64
}

type Config struct {
	CameraIndex int
	ModelPath   string
	Width       int
	Height      int
	FPS         float64
	// Preview opens the OpenCV debug window from the camera loop. It
	// needs a display and the camera loop's thread; Q quits the loop.
	Preview bool
}

func DefaultConfig(modelPath string) Config {
	return Config{CameraIndex: 0, ModelPath: modelPath, Width: 640, Height: 480, FPS: 15}
}

type FaceDetection struct {
	X          float32
	Y          float32
	Width      float32
	Height     float32
	Confidence float32
}

type TrackerConfig struct {
	FrameWidth      int
	FrameHeight     int
	SmoothingAlpha  float64
	LostAfter       time.Duration
	Hysteresis      float64
	ProximityWeight float64
}

func DefaultTrackerConfig() TrackerConfig {
	return TrackerConfig{
		FrameWidth:      640,
		FrameHeight:     480,
		SmoothingAlpha:  0.35,
		LostAfter:       300 * time.Millisecond,
		Hysteresis:      0.10,
		ProximityWeight: 0.25,
	}
}

type TemporalTracker struct {
	config        TrackerConfig
	hasTarget     bool
	lastRaw       Target
	smoothed      Target
	lastSeen      time.Time
	lastDetection FaceDetection
}

func NewTemporalTracker(config TrackerConfig) *TemporalTracker {
	if config.FrameWidth <= 0 || config.FrameHeight <= 0 {
		defaults := DefaultTrackerConfig()
		if config.FrameWidth <= 0 {
			config.FrameWidth = defaults.FrameWidth
		}
		if config.FrameHeight <= 0 {
			config.FrameHeight = defaults.FrameHeight
		}
	}
	if config.SmoothingAlpha <= 0 || config.SmoothingAlpha > 1 {
		config.SmoothingAlpha = 0.35
	}
	if config.LostAfter <= 0 {
		config.LostAfter = 300 * time.Millisecond
	}
	if config.Hysteresis < 0 {
		config.Hysteresis = 0.10
	}
	if config.ProximityWeight < 0 {
		config.ProximityWeight = 0.25
	}
	return &TemporalTracker{config: config}
}

func (tracker *TemporalTracker) Update(detections []FaceDetection, now time.Time) *Target {
	if tracker == nil {
		return nil
	}
	if len(detections) == 0 {
		if tracker.hasTarget && now.Sub(tracker.lastSeen) <= tracker.config.LostAfter {
			target := tracker.smoothed
			return &target
		}
		tracker.hasTarget = false
		return nil
	}

	selected := tracker.selectDetection(detections)
	raw := tracker.normalize(selected)
	if !tracker.hasTarget {
		tracker.smoothed = raw
	} else {
		alpha := tracker.config.SmoothingAlpha
		tracker.smoothed.X = tracker.smoothed.X + alpha*(raw.X-tracker.smoothed.X)
		tracker.smoothed.Y = tracker.smoothed.Y + alpha*(raw.Y-tracker.smoothed.Y)
	}
	tracker.lastRaw = raw
	tracker.lastDetection = selected
	tracker.lastSeen = now
	tracker.hasTarget = true
	target := tracker.smoothed
	return &target
}

func (tracker *TemporalTracker) selectDetection(detections []FaceDetection) FaceDetection {
	best := detections[0]
	bestScore := tracker.detectionScore(best, false)
	for _, detection := range detections[1:] {
		score := tracker.detectionScore(detection, false)
		if score > bestScore {
			best, bestScore = detection, score
		}
	}
	if !tracker.hasTarget {
		return best
	}

	current := detections[0]
	currentDistance := tracker.distance(current)
	for _, detection := range detections[1:] {
		if distance := tracker.distance(detection); distance < currentDistance {
			current, currentDistance = detection, distance
		}
	}
	currentScore := tracker.detectionScore(current, true)
	if currentScore+tracker.config.Hysteresis >= bestScore {
		return current
	}
	return best
}

func (tracker *TemporalTracker) detectionScore(detection FaceDetection, includeProximity bool) float64 {
	area := float64(detection.Width*detection.Height) / float64(tracker.config.FrameWidth*tracker.config.FrameHeight)
	if area < 0 {
		area = 0
	}
	if area > 1 {
		area = 1
	}
	score := float64(detection.Confidence) + 0.20*area
	if includeProximity && tracker.hasTarget {
		score += tracker.config.ProximityWeight * (1 - tracker.distance(detection))
	}
	return score
}

func (tracker *TemporalTracker) distance(detection FaceDetection) float64 {
	center := tracker.normalize(detection)
	dx := center.X - tracker.lastRaw.X
	dy := center.Y - tracker.lastRaw.Y
	distance := (dx*dx + dy*dy) / 4
	if distance > 1 {
		return 1
	}
	return distance
}

func (tracker *TemporalTracker) normalize(detection FaceDetection) Target {
	centerX := float64(detection.X + detection.Width/2)
	centerY := float64(detection.Y + detection.Height/2)
	return Target{
		X: clamp(centerX/float64(tracker.config.FrameWidth)*2-1, -1, 1),
		Y: clamp(centerY/float64(tracker.config.FrameHeight)*2-1, -1, 1),
	}
}

func clamp(value, low, high float64) float64 {
	if value < low {
		return low
	}
	if value > high {
		return high
	}
	return value
}

type SnapshotStore struct {
	mu       sync.RWMutex
	snapshot *PerceptionSnapshot
}

func NewSnapshotStore() *SnapshotStore { return &SnapshotStore{} }

func (store *SnapshotStore) Publish(snapshot PerceptionSnapshot) {
	if store == nil {
		return
	}
	copy := snapshot
	if snapshot.Target != nil {
		target := *snapshot.Target
		copy.Target = &target
	}
	store.mu.Lock()
	store.snapshot = &copy
	store.mu.Unlock()
}

func (store *SnapshotStore) Load() *PerceptionSnapshot {
	if store == nil {
		return nil
	}
	store.mu.RLock()
	defer store.mu.RUnlock()
	if store.snapshot == nil {
		return nil
	}
	copy := *store.snapshot
	if store.snapshot.Target != nil {
		target := *store.snapshot.Target
		copy.Target = &target
	}
	return &copy
}

// PublishLatestTarget replaces a queued target instead of building a backlog.
func PublishLatestTarget(channel chan Target, target Target) {
	select {
	case channel <- target:
		return
	default:
	}
	select {
	case <-channel:
	default:
	}
	select {
	case channel <- target:
	default:
	}
}

type DebugSample struct {
	Snapshot     PerceptionSnapshot
	RawTarget    *Target
	SmoothTarget *Target
	Read         time.Duration
	Detect       time.Duration
	Loop         time.Duration
}

// RunCamera owns the camera for its entire lifetime and publishes only the
// latest perception and target. It contains no product or actuator decisions.
func RunCamera(ctx context.Context, config Config, tracker *TemporalTracker,
	publish func(PerceptionSnapshot), publishTarget func(Target), debug func(DebugSample)) error {
	camera, err := Open(config)
	if err != nil {
		return err
	}
	defer camera.Close()
	if tracker == nil {
		tracker = NewTemporalTracker(DefaultTrackerConfig())
	}
	detections := make([]FaceDetection, maxDetections)
	lastDebug := time.Time{}
	for ctx.Err() == nil {
		loopStarted := time.Now()
		readStarted := time.Now()
		if err := camera.Read(); err != nil {
			if ctx.Err() != nil {
				return nil
			}
			return err
		}
		readDuration := time.Since(readStarted)
		if ctx.Err() != nil {
			return nil
		}
		detectStarted := time.Now()
		count, err := camera.Detect(detections)
		if err != nil {
			if ctx.Err() != nil {
				return nil
			}
			return err
		}
		detectDuration := time.Since(detectStarted)
		if ctx.Err() != nil {
			return nil
		}
		now := time.Now()
		target := tracker.Update(detections[:count], now)
		snapshot := PerceptionSnapshot{
			FaceVisible: len(detections[:count]) > 0,
			FaceCount:   count,
			Target:      target,
			UpdatedAt:   now,
		}
		if publish != nil {
			publish(snapshot)
		}
		if count > 0 && target != nil && publishTarget != nil {
			publishTarget(*target)
		}
		if config.Preview {
			keepGoing, err := camera.Preview(detections[:count])
			if err != nil {
				if ctx.Err() != nil {
					return nil
				}
				return err
			}
			if !keepGoing {
				return nil
			}
		}
		if debug != nil && (lastDebug.IsZero() || time.Since(lastDebug) >= time.Second) {
			var raw, smooth *Target
			if target != nil {
				rawValue := tracker.lastRaw
				smoothValue := tracker.smoothed
				raw = &rawValue
				smooth = &smoothValue
			}
			debug(DebugSample{Snapshot: snapshot, RawTarget: raw, SmoothTarget: smooth, Read: readDuration, Detect: detectDuration, Loop: time.Since(loopStarted)})
			lastDebug = time.Now()
		}
	}
	return nil
}

// PerceptionSnapshot es la salida estable de Vision hacia el resto del sistema.
type PerceptionSnapshot struct {
	FaceVisible   bool
	PersonVisible bool
	FaceCount     int
	Target        *Target
	UpdatedAt     time.Time
}

type Face struct {
	X float64
	Y float64
}

type Person struct {
	X float64
	Y float64
}

type FaceDetector interface {
	DetectFaces([]byte) ([]Face, error)
}

type PersonDetector interface {
	DetectPersons([]byte) ([]Person, error)
}

type Tracker interface {
	Track([]Face, []Person) *Target
}

// Vision coordina detectores y tracker inyectados. Las implementaciones
// concretas pueden usar OpenCV, ONNX u otra librería sin afectar este contrato.
type Vision struct {
	FaceDetector   FaceDetector
	PersonDetector PersonDetector
	Tracker        Tracker
}

func (v *Vision) Analyze(frame []byte) (PerceptionSnapshot, error) {
	var faces []Face
	var persons []Person
	var err error
	if v != nil && v.FaceDetector != nil {
		faces, err = v.FaceDetector.DetectFaces(frame)
		if err != nil {
			return PerceptionSnapshot{}, err
		}
	}
	if v != nil && v.PersonDetector != nil {
		persons, err = v.PersonDetector.DetectPersons(frame)
		if err != nil {
			return PerceptionSnapshot{}, err
		}
	}
	var target *Target
	if v != nil && v.Tracker != nil {
		target = v.Tracker.Track(faces, persons)
	}
	return PerceptionSnapshot{
		FaceVisible:   len(faces) > 0,
		PersonVisible: len(persons) > 0,
		FaceCount:     len(faces),
		Target:        target,
		UpdatedAt:     time.Now(),
	}, nil
}

// DetectFaces mantiene una implementación explícita para consumidores que
// todavía usan Vision como detector de caras independiente.
func (v *Vision) DetectFaces(frame []byte) ([]Face, error) {
	if v == nil || v.FaceDetector == nil {
		return nil, nil
	}
	return v.FaceDetector.DetectFaces(frame)
}

func (v *Vision) DetectPersons(frame []byte) ([]Person, error) {
	if v == nil || v.PersonDetector == nil {
		return nil, nil
	}
	return v.PersonDetector.DetectPersons(frame)
}
