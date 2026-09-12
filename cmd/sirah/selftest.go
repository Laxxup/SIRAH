package main

import (
	"context"
	"fmt"
	"os"
	"time"

	"github.com/Laxxup/SIRAH/internal/firmware"
	"github.com/Laxxup/SIRAH/internal/motion"
	"github.com/Laxxup/SIRAH/internal/sirah"
	"github.com/Laxxup/SIRAH/internal/vision"
)

// runSelftest executes a deterministic hardware check without the LLM:
// handshake, CENTER, BLINK, MODE FACE, one vision TARGET from a real face,
// back to IDLE. Each step prints PASS/FAIL. Returns the process exit code.
func runSelftest(parent context.Context, debug bool) int {
	ctx, cancel := context.WithTimeout(parent, 90*time.Second)
	defer cancel()
	failures := 0
	check := func(name string, err error) bool {
		if err != nil {
			fmt.Printf("SELFTEST %s: FAIL - %s\n", name, err)
			failures++
			return false
		}
		fmt.Printf("SELFTEST %s: PASS\n", name)
		return true
	}

	serialFile := openSerial(os.Getenv("FIRMWARE_SERIAL"), envInt("FIRMWARE_BAUD", 115200))
	if serialFile == nil {
		fmt.Printf("SELFTEST serial: FAIL - cannot open %s\n", os.Getenv("FIRMWARE_SERIAL"))
		return 1
	}
	serialDevice := firmware.NewSerial(serialFile)
	defer serialDevice.Close()
	serialDevice.Reader = serialFile
	if err := serialDevice.Start(ctx); err != nil {
		fmt.Printf("SELFTEST serial: FAIL - reader: %s\n", err)
		return 1
	}
	if err := handshakeFirmware(ctx, serialDevice); err != nil {
		fmt.Printf("SELFTEST serial: FAIL - %s\n", err)
		return 1
	}
	fmt.Printf("SELFTEST serial: PASS\n")

	mot := motion.New(serialDevice)
	eventsCtx, stopEvents := context.WithCancel(ctx)
	eventsDone := make(chan struct{})
	go func() {
		defer close(eventsDone)
		runFirmwareEvents(eventsCtx, serialDevice.Events(), mot)
	}()
	defer func() {
		stopEvents()
		<-eventsDone
	}()
	if !check("center", mot.Execute(sirah.ActionCenter)) {
		return 1
	}
	if debug {
		_, _, health, delivery, _ := mot.Snapshot()
		fmt.Printf("SELFTEST detail: delivery=%s health=%s\n", delivery, health)
	}
	time.Sleep(400 * time.Millisecond)
	if !check("blink", mot.Execute(sirah.ActionBlink)) {
		return 1
	}
	time.Sleep(400 * time.Millisecond)
	if !check("tired", mot.Execute(sirah.ActionTired)) {
		return 1
	}
	time.Sleep(1100 * time.Millisecond)
	if !check("mode-face", mot.Execute(sirah.ActionLookAtUser)) {
		return 1
	}

	visionConfig := vision.DefaultConfig(envString("VISION_MODEL", "models/face_detection_yunet_2023mar.onnx"))
	visionConfig.CameraIndex = envInt("VISION_CAMERA_INDEX", 0)
	tracker := vision.NewTemporalTracker(vision.DefaultTrackerConfig())
	targets := make(chan vision.Target, 1)
	visionCtx, visionCancel := context.WithTimeout(ctx, 25*time.Second)
	defer visionCancel()
	visionDone := make(chan error, 1)
	go func() {
		visionDone <- vision.RunCamera(visionCtx, visionConfig, tracker,
			func(vision.PerceptionSnapshot) {},
			func(target vision.Target) { vision.PublishLatestTarget(targets, target) },
			nil)
	}()
	var target vision.Target
	select {
	case target = <-targets:
		fmt.Printf("SELFTEST face-target: PASS (x=%.3f y=%.3f) - ponte frente a la camara si falla\n", target.X, target.Y)
	case <-visionCtx.Done():
		fmt.Printf("SELFTEST face-target: FAIL - no face in front of the camera within 25s\n")
		_ = mot.Execute(sirah.ActionStopLooking)
		return 1
	}
	visionCancel()
	<-visionDone
	if !check("target", mot.UpdateTarget(motion.Target{X: target.X, Y: target.Y})) {
		return 1
	}
	if debug {
		_, _, health, delivery, _ := mot.Snapshot()
		fmt.Printf("SELFTEST detail: delivery=%s health=%s\n", delivery, health)
	}
	time.Sleep(600 * time.Millisecond)
	check("mode-idle", mot.Execute(sirah.ActionStopLooking))

	if failures > 0 {
		fmt.Printf("SELFTEST: %d FAILURES\n", failures)
		return 1
	}
	fmt.Printf("SELFTEST: ALL PASS\n")
	return 0
}
