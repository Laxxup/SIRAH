#include "bridge.h"

#include <opencv2/highgui.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/objdetect/face.hpp>
#include <opencv2/videoio.hpp>

#include <algorithm>
#include <cstdio>
#include <exception>
#include <memory>
#include <string>

struct vision_handle {
    cv::VideoCapture camera;
    cv::Ptr<cv::FaceDetectorYN> detector;
    cv::Mat frame;
    cv::Mat detections;
    bool frame_ready = false;
};

namespace {

void clear_error(char *error, size_t error_size) {
    if (error != nullptr && error_size > 0) {
        error[0] = '\0';
    }
}

void set_error(char *error, size_t error_size, const char *message) {
    if (error != nullptr && error_size > 0) {
        std::snprintf(error, error_size, "%s", message != nullptr ? message : "native vision error");
    }
}

void set_exception(char *error, size_t error_size, const std::exception &exception) {
    set_error(error, error_size, exception.what());
}

}  // namespace

int vision_open(int camera_index, const char *model_path, int width, int height,
                double fps, vision_handle_t **out, char *error, size_t error_size) {
    clear_error(error, error_size);
    if (out == nullptr || model_path == nullptr || model_path[0] == '\0' ||
        camera_index < 0 || width <= 0 || height <= 0 || fps <= 0.0) {
        set_error(error, error_size, "invalid vision_open arguments");
        return VISION_ERR_ARGUMENT;
    }
    *out = nullptr;

    try {
        std::unique_ptr<vision_handle_t> candidate(new vision_handle_t());
        candidate->camera.open(camera_index, cv::CAP_V4L2);
        if (!candidate->camera.isOpened()) {
            set_error(error, error_size, "cannot open camera with V4L2 backend");
            return VISION_ERR_OPEN_CAMERA;
        }
        candidate->camera.set(cv::CAP_PROP_FRAME_WIDTH, width);
        candidate->camera.set(cv::CAP_PROP_FRAME_HEIGHT, height);
        candidate->camera.set(cv::CAP_PROP_FPS, fps);

        candidate->detector = cv::FaceDetectorYN::create(
            model_path, "", cv::Size(width, height), 0.9f, 0.3f, 5000, 0, 0);
        if (candidate->detector.empty()) {
            set_error(error, error_size, "cannot create YuNet detector from model");
            return VISION_ERR_OPEN_MODEL;
        }

        *out = candidate.release();
        return VISION_OK;
    } catch (const cv::Exception &exception) {
        set_exception(error, error_size, exception);
        return VISION_ERR_NATIVE;
    } catch (const std::exception &exception) {
        set_exception(error, error_size, exception);
        return VISION_ERR_NATIVE;
    } catch (...) {
        set_error(error, error_size, "unknown native vision error");
        return VISION_ERR_NATIVE;
    }
}

int vision_read(vision_handle_t *handle, char *error, size_t error_size) {
    clear_error(error, error_size);
    if (handle == nullptr) {
        set_error(error, error_size, "invalid vision handle");
        return VISION_ERR_ARGUMENT;
    }

    try {
        handle->frame_ready = handle->camera.read(handle->frame);
        if (!handle->frame_ready || handle->frame.empty()) {
            set_error(error, error_size, "cannot read frame from camera");
            return VISION_ERR_READ_FRAME;
        }
        if (handle->detector->getInputSize() != handle->frame.size()) {
            handle->detector->setInputSize(handle->frame.size());
        }
        return VISION_OK;
    } catch (const cv::Exception &exception) {
        set_exception(error, error_size, exception);
        return VISION_ERR_NATIVE;
    } catch (const std::exception &exception) {
        set_exception(error, error_size, exception);
        return VISION_ERR_NATIVE;
    } catch (...) {
        set_error(error, error_size, "unknown native vision error");
        return VISION_ERR_NATIVE;
    }
}

int vision_detect(vision_handle_t *handle, vision_face_detection_t *detections,
                  size_t capacity, size_t *count, char *error, size_t error_size) {
    clear_error(error, error_size);
    if (handle == nullptr || count == nullptr || (capacity > 0 && detections == nullptr)) {
        set_error(error, error_size, "invalid vision_detect arguments");
        return VISION_ERR_ARGUMENT;
    }
    *count = 0;
    if (!handle->frame_ready) {
        set_error(error, error_size, "vision_read must succeed before vision_detect");
        return VISION_ERR_NO_FRAME;
    }

    try {
        handle->detector->detect(handle->frame, handle->detections);
        const size_t detected = handle->detections.empty() ? 0 : static_cast<size_t>(handle->detections.rows);
        *count = detected;
        if (detected > capacity) {
            set_error(error, error_size, "detection output buffer is too small");
            return VISION_ERR_CAPACITY;
        }

        for (size_t i = 0; i < detected; ++i) {
            const float *row = handle->detections.ptr<float>(static_cast<int>(i));
            detections[i] = vision_face_detection_t{row[0], row[1], row[2], row[3], row[14]};
        }
        return VISION_OK;
    } catch (const cv::Exception &exception) {
        set_exception(error, error_size, exception);
        return VISION_ERR_NATIVE;
    } catch (const std::exception &exception) {
        set_exception(error, error_size, exception);
        return VISION_ERR_NATIVE;
    } catch (...) {
        set_error(error, error_size, "unknown native vision error");
        return VISION_ERR_NATIVE;
    }
}

void vision_close(vision_handle_t *handle) {
    if (handle == nullptr) {
        return;
    }
    try {
        cv::destroyAllWindows();
    } catch (...) {
        // Continue releasing native resources even if the GUI backend is already gone.
    }
    handle->detector.release();
    handle->camera.release();
    handle->frame.release();
    handle->detections.release();
    delete handle;
}

int vision_preview(vision_handle_t *handle, const vision_face_detection_t *detections,
                   size_t count, char *error, size_t error_size) {
    clear_error(error, error_size);
    if (handle == nullptr || (count > 0 && detections == nullptr)) {
        set_error(error, error_size, "invalid vision_preview arguments");
        return VISION_ERR_ARGUMENT;
    }
    if (!handle->frame_ready) {
        set_error(error, error_size, "vision_read must succeed before vision_preview");
        return VISION_ERR_NO_FRAME;
    }

    try {
        cv::Mat preview = handle->frame.clone();
        for (size_t i = 0; i < count; ++i) {
            const vision_face_detection_t &detection = detections[i];
            const cv::Rect box(
                cvRound(detection.x), cvRound(detection.y),
                cvRound(detection.width), cvRound(detection.height));
            cv::rectangle(preview, box, cv::Scalar(0, 255, 0), 2);
            cv::putText(preview, cv::format("%.3f", detection.confidence),
                        cv::Point(box.x, std::max(0, box.y - 5)),
                        cv::FONT_HERSHEY_SIMPLEX, 0.5, cv::Scalar(0, 255, 0), 1);
        }
        cv::imshow("SIRAH Vision", preview);
        const int key = cv::waitKey(1);
        const double visible = cv::getWindowProperty("SIRAH Vision", cv::WND_PROP_VISIBLE);
        if (key == 'q' || key == 'Q' || key == 27 || visible < 1.0) {
            cv::destroyWindow("SIRAH Vision");
            return VISION_PREVIEW_QUIT;
        }
        return VISION_OK;
    } catch (const cv::Exception &exception) {
        set_exception(error, error_size, exception);
        return VISION_ERR_NATIVE;
    } catch (const std::exception &exception) {
        set_exception(error, error_size, exception);
        return VISION_ERR_NATIVE;
    } catch (...) {
        set_error(error, error_size, "unknown native vision error");
        return VISION_ERR_NATIVE;
    }
}
