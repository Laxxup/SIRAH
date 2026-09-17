package vision

import (
	"context"
	"errors"
	"image"
	"testing"
	"time"
)

func TestAnalyzeWithoutDetectorsIsSafe(t *testing.T) {
	snapshot, err := (&Vision{}).Analyze(nil)
	if err != nil {
		t.Fatal(err)
	}
	if snapshot.FaceVisible || snapshot.PersonVisible {
		t.Fatalf("unexpected detections: %#v", snapshot)
	}
	if snapshot.Presence != PresenceUnavailable {
		t.Fatalf("presence = %q, want unavailable", snapshot.Presence)
	}
}

func TestDetectionImageRectConvertsPixelBounds(t *testing.T) {
	detection := FaceDetection{X: 10.5, Y: 20.25, Width: 30.75, Height: 40.5}
	got := detectionImageRect(detection)
	want := image.Rect(10, 20, 41, 60)
	if got != want {
		t.Fatalf("rectangle = %v, want %v", got, want)
	}
}

func TestOpenRejectsInvalidConfigWithoutCamera(t *testing.T) {
	if _, err := Open(Config{CameraIndex: -1, ModelPath: "missing.onnx", Width: 640, Height: 480, FPS: 15}); err == nil {
		t.Fatal("expected invalid configuration error")
	}
}

func TestRetryReadRecoversFromTransientFailure(t *testing.T) {
	attempts := 0
	err := retryRead(func() error {
		attempts++
		if attempts < 3 {
			return errors.New("temporary read failure")
		}
		return nil
	}, 3, 0)
	if err != nil {
		t.Fatal(err)
	}
	if attempts != 3 {
		t.Fatalf("attempts = %d, want 3", attempts)
	}
}

func TestRetryReadReturnsPersistentFailure(t *testing.T) {
	want := errors.New("persistent read failure")
	attempts := 0
	err := retryRead(func() error {
		attempts++
		return want
	}, 3, time.Nanosecond)
	if !errors.Is(err, want) {
		t.Fatalf("error = %v, want %v", err, want)
	}
	if attempts != 3 {
		t.Fatalf("attempts = %d, want 3", attempts)
	}
}

func TestTemporalTrackerNormalizesFaceCenter(t *testing.T) {
	tracker := NewTemporalTracker(TrackerConfig{FrameWidth: 640, FrameHeight: 480, SmoothingAlpha: 1, LostAfter: time.Second})
	target := tracker.Update([]FaceDetection{{X: 288, Y: 192, Width: 64, Height: 96, Confidence: 0.9}}, time.Unix(1, 0))
	if target == nil {
		t.Fatal("expected target")
	}
	if target.X != 0 || target.Y != 0 {
		t.Fatalf("target = %#v, want centered target", target)
	}
}

func TestTemporalTrackerUsesConfidenceAndAreaInitially(t *testing.T) {
	tracker := NewTemporalTracker(TrackerConfig{FrameWidth: 640, FrameHeight: 480, SmoothingAlpha: 1})
	target := tracker.Update([]FaceDetection{
		{X: 0, Y: 0, Width: 32, Height: 32, Confidence: 0.80},
		{X: 320, Y: 0, Width: 320, Height: 240, Confidence: 0.85},
	}, time.Unix(1, 0))
	if target == nil || target.X <= 0 {
		t.Fatalf("target = %#v, expected larger high-area face", target)
	}
}

func TestTemporalTrackerHysteresisKeepsNearbyTarget(t *testing.T) {
	tracker := NewTemporalTracker(TrackerConfig{FrameWidth: 640, FrameHeight: 480, SmoothingAlpha: 1, Hysteresis: 0.10, ProximityWeight: 0.25})
	first := tracker.Update([]FaceDetection{{X: 250, Y: 180, Width: 80, Height: 80, Confidence: 0.90}}, time.Unix(1, 0))
	second := tracker.Update([]FaceDetection{
		{X: 255, Y: 180, Width: 80, Height: 80, Confidence: 0.88},
		{X: 500, Y: 180, Width: 100, Height: 100, Confidence: 0.95},
	}, time.Unix(1, int64(30*time.Millisecond)))
	if first == nil || second == nil || second.X >= 0.5 {
		t.Fatalf("first=%#v second=%#v, expected nearby target to win", first, second)
	}
}

func TestTemporalTrackerKeepsThenLosesTarget(t *testing.T) {
	tracker := NewTemporalTracker(TrackerConfig{FrameWidth: 640, FrameHeight: 480, SmoothingAlpha: 1, LostAfter: 300 * time.Millisecond})
	seenAt := time.Unix(1, 0)
	if tracker.Update([]FaceDetection{{X: 288, Y: 192, Width: 64, Height: 96, Confidence: 0.9}}, seenAt) == nil {
		t.Fatal("expected initial target")
	}
	if tracker.Update(nil, seenAt.Add(200*time.Millisecond)) == nil {
		t.Fatal("expected brief loss to retain target")
	}
	if tracker.Update(nil, seenAt.Add(301*time.Millisecond)) != nil {
		t.Fatal("expected target to be lost after tolerance")
	}
}

func TestTemporalTrackerReportsPresenceTransitions(t *testing.T) {
	tracker := NewTemporalTracker(TrackerConfig{
		FrameWidth:   640,
		FrameHeight:  480,
		StableFrames: 2,
		LostAfter:    300 * time.Millisecond,
	})
	face := []FaceDetection{{X: 288, Y: 192, Width: 64, Height: 96, Confidence: 0.9}}
	seenAt := time.Unix(1, 0)

	target := tracker.Update(face, seenAt)
	if got := presenceForDetection(len(face), target, tracker.targetStable()); got != PresenceVisible {
		t.Fatalf("first presence = %q, want visible", got)
	}
	target = tracker.Update(face, seenAt.Add(10*time.Millisecond))
	if got := presenceForDetection(len(face), target, tracker.targetStable()); got != PresenceStable {
		t.Fatalf("stable presence = %q, want stable", got)
	}
	target = tracker.Update(nil, seenAt.Add(200*time.Millisecond))
	if got := presenceForDetection(0, target, tracker.targetStable()); got != PresenceRecentlyLost {
		t.Fatalf("recent loss presence = %q, want recently_lost", got)
	}
	target = tracker.Update(nil, seenAt.Add(311*time.Millisecond))
	if got := presenceForDetection(0, target, tracker.targetStable()); got != PresenceAbsent {
		t.Fatalf("confirmed absence presence = %q, want absent", got)
	}
	target = tracker.Update(face, seenAt.Add(400*time.Millisecond))
	if got := presenceForDetection(len(face), target, tracker.targetStable()); got != PresenceVisible {
		t.Fatalf("reappearance presence = %q, want visible", got)
	}
	target = tracker.Update(face, seenAt.Add(410*time.Millisecond))
	if got := presenceForDetection(len(face), target, tracker.targetStable()); got != PresenceStable {
		t.Fatalf("reappearance stable presence = %q, want stable", got)
	}
}

func TestPerceptionSnapshotMarksStaleWithoutChangingStoredState(t *testing.T) {
	updatedAt := time.Unix(10, 0)
	snapshot := PerceptionSnapshot{Presence: PresenceStable, UpdatedAt: updatedAt}
	if got := snapshot.PresenceAt(updatedAt.Add(500*time.Millisecond), time.Second); got != PresenceStable {
		t.Fatalf("fresh presence = %q, want stable", got)
	}
	if got := snapshot.PresenceAt(updatedAt.Add(2*time.Second), time.Second); got != PresenceStale {
		t.Fatalf("stale presence = %q, want stale", got)
	}
	if snapshot.Presence != PresenceStable {
		t.Fatalf("stored presence = %q, want stable", snapshot.Presence)
	}
}

func TestPerceptionSnapshotWithoutStateIsUnavailable(t *testing.T) {
	snapshot := PerceptionSnapshot{FaceVisible: true, FaceCount: 1, UpdatedAt: time.Unix(10, 0)}
	if got := snapshot.PresenceAt(time.Unix(10, 0), time.Second); got != PresenceUnavailable {
		t.Fatalf("presence = %q, want unavailable", got)
	}
}

func TestPerceptionSnapshotDoesNotPersistStaleState(t *testing.T) {
	snapshot := PerceptionSnapshot{Presence: PresenceStale, UpdatedAt: time.Unix(10, 0)}
	if got := snapshot.PresenceAt(time.Unix(10, 0), time.Second); got != PresenceUnavailable {
		t.Fatalf("stored stale presence = %q, want unavailable", got)
	}
}

func TestSnapshotStoreCopiesLatestValue(t *testing.T) {
	store := NewSnapshotStore()
	target := Target{X: 0.2, Y: -0.1}
	store.Publish(PerceptionSnapshot{FaceVisible: true, FaceCount: 1, Target: &target, UpdatedAt: time.Now()})
	target.X = 0.9
	got := store.Load()
	if got == nil || got.Target == nil || got.Target.X != 0.2 {
		t.Fatalf("snapshot = %#v, expected copied target", got)
	}
}

func TestPublishLatestTargetDropsQueuedValue(t *testing.T) {
	channel := make(chan Target, 1)
	PublishLatestTarget(channel, Target{X: 0.1})
	PublishLatestTarget(channel, Target{X: 0.9})
	if got := <-channel; got.X != 0.9 {
		t.Fatalf("target = %#v, want latest target", got)
	}
}

func TestRunCameraUnavailableReturnsErrorWithoutBreakingCaller(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	var snapshot PerceptionSnapshot
	err := RunCamera(ctx, Config{CameraIndex: -1, ModelPath: "missing.onnx", Width: 640, Height: 480, FPS: 15}, nil, func(value PerceptionSnapshot) { snapshot = value }, nil, nil)
	if err == nil {
		t.Fatal("expected unavailable camera error")
	}
	if snapshot.Presence != PresenceUnavailable {
		t.Fatalf("presence = %q, want unavailable", snapshot.Presence)
	}
}
