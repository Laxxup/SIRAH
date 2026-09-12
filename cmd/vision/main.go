package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"runtime"
	"syscall"
	"time"

	"github.com/Laxxup/SIRAH/internal/vision"
)

func main() {
	model := flag.String("model", "models/face_detection_yunet_2023mar.onnx", "YuNet ONNX model")
	cameraIndex := flag.Int("camera", 0, "V4L2 camera index")
	debug := flag.Bool("debug", false, "print raw face detections")
	preview := flag.Bool("preview", false, "show debug preview window")
	flag.Parse()

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	if *preview {
		runtime.LockOSThread()
		defer runtime.UnlockOSThread()
	}

	config := vision.DefaultConfig(*model)
	config.CameraIndex = *cameraIndex
	camera, err := vision.Open(config)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Vision: %s\n", err)
		os.Exit(1)
	}
	defer camera.Close()

	detections := make([]vision.FaceDetection, 128)
	for {
		if ctx.Err() != nil {
			return
		}
		loopStarted := time.Now()

		readStarted := time.Now()
		if err := camera.Read(); err != nil {
			fmt.Fprintf(os.Stderr, "Vision: %s\n", err)
			return
		}
		readDuration := time.Since(readStarted)
		if ctx.Err() != nil {
			return
		}

		detectStarted := time.Now()
		count, err := camera.Detect(detections)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Vision: %s\n", err)
			return
		}
		detectDuration := time.Since(detectStarted)
		if ctx.Err() != nil {
			return
		}

		previewDuration := time.Duration(0)
		if *preview {
			previewStarted := time.Now()
			keepGoing, err := camera.Preview(detections[:count])
			previewDuration = time.Since(previewStarted)
			if err != nil {
				fmt.Fprintf(os.Stderr, "Vision: preview: %s\n", err)
				return
			}
			if !keepGoing {
				return
			}
		}
		if ctx.Err() != nil {
			return
		}

		if *debug {
			fmt.Printf("faces=%d\n", count)
			for i := 0; i < count; i++ {
				detection := detections[i]
				fmt.Printf("bbox=(%.1f,%.1f,%.1f,%.1f) confidence=%.4f\n", detection.X, detection.Y, detection.Width, detection.Height, detection.Confidence)
			}
			fmt.Printf("timings read_ms=%.1f detect_ms=%.1f preview_ms=%.1f loop_ms=%.1f\n",
				milliseconds(readDuration), milliseconds(detectDuration), milliseconds(previewDuration), milliseconds(time.Since(loopStarted)))
		}
	}
}

func milliseconds(duration time.Duration) float64 {
	return float64(duration.Microseconds()) / 1000
}
