//go:build linux && cgo && opencv4

package vision

// Mirror of vision_cgo.go for systems with OpenCV 4 (pkg-config opencv4)
// instead of OpenCV 5, e.g. Fedora. The YuNet bridge API used here exists in
// both. Build with: go build -tags opencv4 ./...
// Keep in sync with vision_cgo.go; only the build tag and pkg-config name differ.

/*
#cgo pkg-config: opencv4
#cgo CXXFLAGS: -std=c++11 -DNDEBUG
#cgo LDFLAGS: -lstdc++ -Wl,--as-needed -Wl,--allow-shlib-undefined
#include "bridge.h"
#include <stdlib.h>
*/
import "C"

import (
	"fmt"
	"image"
	"time"
	"unsafe"
)

const readAttempts = 3
const readRetryDelay = 50 * time.Millisecond

type Camera struct {
	handle *C.vision_handle_t
}

func Open(config Config) (*Camera, error) {
	modelPath := C.CString(config.ModelPath)
	defer C.free(unsafe.Pointer(modelPath))
	var errorBuffer [512]byte
	var handle *C.vision_handle_t
	result := C.vision_open(
		C.int(config.CameraIndex), modelPath, C.int(config.Width), C.int(config.Height), C.double(config.FPS),
		&handle, (*C.char)(unsafe.Pointer(&errorBuffer[0])), C.size_t(len(errorBuffer)),
	)
	if result != C.VISION_OK {
		return nil, nativeError(result, errorBuffer[:])
	}
	return &Camera{handle: handle}, nil
}

func (camera *Camera) Read() error {
	if camera == nil || camera.handle == nil {
		return fmt.Errorf("vision: camera is closed")
	}
	return retryRead(func() error {
		var errorBuffer [512]byte
		result := C.vision_read(camera.handle, (*C.char)(unsafe.Pointer(&errorBuffer[0])), C.size_t(len(errorBuffer)))
		if result != C.VISION_OK {
			return nativeError(result, errorBuffer[:])
		}
		return nil
	}, readAttempts, readRetryDelay)
}

func (camera *Camera) Detect(dst []FaceDetection) (int, error) {
	if camera == nil || camera.handle == nil {
		return 0, fmt.Errorf("vision: camera is closed")
	}
	if len(dst) == 0 {
		return 0, fmt.Errorf("vision: detection buffer must not be empty")
	}
	var nativeDetections [maxDetections]C.vision_face_detection_t
	capacity := len(dst)
	if capacity > len(nativeDetections) {
		capacity = len(nativeDetections)
	}
	var errorBuffer [512]byte
	var count C.size_t
	result := C.vision_detect(
		camera.handle,
		(*C.vision_face_detection_t)(unsafe.Pointer(&nativeDetections[0])), C.size_t(capacity), &count,
		(*C.char)(unsafe.Pointer(&errorBuffer[0])), C.size_t(len(errorBuffer)),
	)
	if result != C.VISION_OK {
		return int(count), nativeError(result, errorBuffer[:])
	}
	for i := 0; i < int(count); i++ {
		dst[i] = FaceDetection{
			X: float32(nativeDetections[i].x), Y: float32(nativeDetections[i].y),
			Width: float32(nativeDetections[i].width), Height: float32(nativeDetections[i].height),
			Confidence: float32(nativeDetections[i].confidence),
		}
	}
	return int(count), nil
}

func (camera *Camera) Close() {
	if camera != nil && camera.handle != nil {
		C.vision_close(camera.handle)
		camera.handle = nil
	}
}

func (camera *Camera) Preview(detections []FaceDetection) (bool, error) {
	if camera == nil || camera.handle == nil {
		return false, fmt.Errorf("vision: camera is closed")
	}
	nativeDetections := make([]C.vision_face_detection_t, len(detections))
	for i, detection := range detections {
		nativeDetections[i] = C.vision_face_detection_t{
			x: C.float(detection.X), y: C.float(detection.Y),
			width: C.float(detection.Width), height: C.float(detection.Height),
			confidence: C.float(detection.Confidence),
		}
	}
	var errorBuffer [512]byte
	var nativePointer *C.vision_face_detection_t
	if len(nativeDetections) > 0 {
		nativePointer = &nativeDetections[0]
	}
	result := C.vision_preview(
		camera.handle, nativePointer, C.size_t(len(nativeDetections)),
		(*C.char)(unsafe.Pointer(&errorBuffer[0])), C.size_t(len(errorBuffer)),
	)
	if result == C.VISION_PREVIEW_QUIT {
		return false, nil
	}
	if result != C.VISION_OK {
		return false, nativeError(result, errorBuffer[:])
	}
	return true, nil
}

func nativeError(code C.int, buffer []byte) error {
	message := "native vision error"
	for i, value := range buffer {
		if value == 0 {
			message = string(buffer[:i])
			break
		}
	}
	return fmt.Errorf("vision: code %d: %s", int(code), message)
}

func detectionImageRect(detection FaceDetection) image.Rectangle {
	return image.Rect(int(detection.X), int(detection.Y), int(detection.X+detection.Width), int(detection.Y+detection.Height))
}
