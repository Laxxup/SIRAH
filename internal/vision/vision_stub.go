//go:build !linux || !cgo

package vision

import (
	"fmt"
	"image"
)

type Camera struct{}

func Open(Config) (*Camera, error) {
	return nil, fmt.Errorf("vision: requires Linux with CGO and OpenCV 4 or 5")
}
func (*Camera) Read() error { return fmt.Errorf("vision: requires Linux with CGO and OpenCV 4 or 5") }
func (*Camera) Detect([]FaceDetection) (int, error) {
	return 0, fmt.Errorf("vision: requires Linux with CGO and OpenCV 4 or 5")
}
func (*Camera) Preview([]FaceDetection) (bool, error) {
	return false, fmt.Errorf("vision: requires Linux with CGO and OpenCV 4 or 5")
}
func (*Camera) Close() {}

func detectionImageRect(detection FaceDetection) image.Rectangle {
	return image.Rect(int(detection.X), int(detection.Y), int(detection.X+detection.Width), int(detection.Y+detection.Height))
}
