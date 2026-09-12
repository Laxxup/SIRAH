package motion

import (
	"bytes"
	"fmt"
	"math"
	"testing"

	"github.com/Laxxup/SIRAH/internal/firmware"
	"github.com/Laxxup/SIRAH/internal/sirah"
)

type statusProbe struct {
	output          bytes.Buffer
	statusCallCount int
}

func (d *statusProbe) Send(command firmware.Command) error {
	return firmware.NewSerial(&d.output).Send(command)
}

func (d *statusProbe) SendWithStatus(firmware.Command) (firmware.DeliveryStatus, error) {
	d.statusCallCount++
	return "", fmt.Errorf("must not wait for status")
}

func TestCenterIsSentAsSemanticFirmwareCommand(t *testing.T) {
	var output bytes.Buffer
	mot := New(firmware.NewSerial(&output))
	if err := mot.Execute(sirah.ActionCenter); err != nil {
		t.Fatal(err)
	}
	if output.String() != "1 CENTER\n" {
		t.Fatalf("output = %q", output.String())
	}
}

func TestTiredIsSentAsSemanticFirmwareCommand(t *testing.T) {
	var output bytes.Buffer
	mot := New(firmware.NewSerial(&output))
	if err := mot.Execute(sirah.ActionTired); err != nil {
		t.Fatal(err)
	}
	if output.String() != "1 TIRED\n" {
		t.Fatalf("output = %q", output.String())
	}
}

func TestUpdateTargetAcceptsNormalizedFiniteValues(t *testing.T) {
	mot := New(firmware.Unavailable{})
	for _, target := range []Target{{X: -1, Y: 1}, {X: 0, Y: 0}} {
		if err := mot.UpdateTarget(target); err != nil {
			t.Fatalf("target=%#v: %v", target, err)
		}
	}
}

func TestUpdateTargetRejectsInvalidValues(t *testing.T) {
	mot := New(firmware.Unavailable{})
	for _, target := range []Target{{X: 1.01}, {X: -1.01}, {X: math.NaN()}, {Y: math.Inf(1)}} {
		if err := mot.UpdateTarget(target); err == nil {
			t.Fatalf("target=%#v was accepted", target)
		}
	}
}

func TestRequestedModeDoesNotImplyAppliedMode(t *testing.T) {
	var output bytes.Buffer
	mot := New(firmware.NewSerial(&output))
	if err := mot.Execute(sirah.ActionLookAtUser); err != nil {
		t.Fatal(err)
	}
	requested, applied, _, delivery, _ := mot.Snapshot()
	if requested != TrackingFace || applied != TrackingIdle {
		t.Fatalf("requested=%q applied=%q", requested, applied)
	}
	if delivery != firmware.DeliverySent {
		t.Fatalf("delivery=%q, want sent", delivery)
	}
	if output.String() != "1 MODE FACE\n" {
		t.Fatalf("output = %q", output.String())
	}
}

func TestFaceTrackingSendsTargetsUntilStopped(t *testing.T) {
	var output bytes.Buffer
	mot := New(firmware.NewSerial(&output))
	if err := mot.Execute(sirah.ActionLookAtUser); err != nil {
		t.Fatal(err)
	}
	if err := mot.UpdateTarget(Target{X: -0.25, Y: 0.5}); err != nil {
		t.Fatal(err)
	}
	if err := mot.Execute(sirah.ActionStopLooking); err != nil {
		t.Fatal(err)
	}
	if err := mot.UpdateTarget(Target{X: 0.75, Y: -0.5}); err != nil {
		t.Fatal(err)
	}
	want := "1 MODE FACE\n2 TARGET -0.250 0.500\n3 MODE IDLE\n"
	if output.String() != want {
		t.Fatalf("output = %q, want %q", output.String(), want)
	}
}

func TestBlinkWhileTrackingDoesNotChangeFaceMode(t *testing.T) {
	var output bytes.Buffer
	mot := New(firmware.NewSerial(&output))
	if err := mot.Execute(sirah.ActionLookAtUser); err != nil {
		t.Fatal(err)
	}
	if err := mot.UpdateTarget(Target{X: -0.5, Y: 0.25}); err != nil {
		t.Fatal(err)
	}
	if err := mot.Execute(sirah.ActionBlink); err != nil {
		t.Fatal(err)
	}
	if err := mot.UpdateTarget(Target{X: 0.5, Y: -0.25}); err != nil {
		t.Fatal(err)
	}
	requested, _, _, _, _ := mot.Snapshot()
	if requested != TrackingFace {
		t.Fatalf("requested mode = %q, want FACE", requested)
	}
	want := "1 MODE FACE\n2 TARGET -0.500 0.250\n3 BLINK\n4 TARGET 0.500 -0.250\n"
	if output.String() != want {
		t.Fatalf("output = %q, want %q", output.String(), want)
	}
}

func TestUnavailableHardwareDegradesWithoutFailingAgentMotion(t *testing.T) {
	mot := New(firmware.Unavailable{})
	if err := mot.Execute(sirah.ActionBlink); err != firmware.ErrUnavailable {
		t.Fatalf("error = %v, want unavailable", err)
	}
	_, _, health, _, _ := mot.Snapshot()
	if health != HardwareDegraded {
		t.Fatalf("health = %q, want degraded", health)
	}
}

func TestMotionNeverWaitsForStatusInRuntimePath(t *testing.T) {
	device := &statusProbe{}
	mot := New(device)
	if err := mot.Execute(sirah.ActionBlink); err != nil {
		t.Fatal(err)
	}
	if device.statusCallCount != 0 {
		t.Fatalf("SendWithStatus calls = %d", device.statusCallCount)
	}
	if device.output.String() != "1 BLINK\n" {
		t.Fatalf("output = %q", device.output.String())
	}
}

func TestTargetsKeepLatestValueWithoutCommandRecords(t *testing.T) {
	var output bytes.Buffer
	mot := New(firmware.NewSerial(&output))
	if err := mot.Execute(sirah.ActionLookAtUser); err != nil {
		t.Fatal(err)
	}
	if err := mot.UpdateTarget(Target{X: -0.4, Y: 0.2}); err != nil {
		t.Fatal(err)
	}
	if err := mot.UpdateTarget(Target{X: 0.8, Y: -0.3}); err != nil {
		t.Fatal(err)
	}
	_, _, _, _, target := mot.Snapshot()
	if target == nil || *target != (Target{X: 0.8, Y: -0.3}) {
		t.Fatalf("latest target = %#v", target)
	}
	if _, _, ok := mot.CommandStatus(2); ok {
		t.Fatal("TARGET command 2 was retained in command records")
	}
	if _, _, ok := mot.CommandStatus(3); ok {
		t.Fatal("TARGET command 3 was retained in command records")
	}
}

func TestNewModeReplacesPreviousPendingModeRecord(t *testing.T) {
	var output bytes.Buffer
	mot := New(firmware.NewSerial(&output))
	if err := mot.Execute(sirah.ActionLookAtUser); err != nil {
		t.Fatal(err)
	}
	if err := mot.Execute(sirah.ActionStopLooking); err != nil {
		t.Fatal(err)
	}
	if _, _, ok := mot.CommandStatus(1); ok {
		t.Fatal("superseded FACE mode record was retained")
	}
	if _, _, ok := mot.CommandStatus(2); !ok {
		t.Fatal("latest IDLE mode record was not retained")
	}
}
