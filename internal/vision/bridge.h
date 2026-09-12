#ifndef SIRAH_VISION_BRIDGE_H
#define SIRAH_VISION_BRIDGE_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct vision_handle vision_handle_t;

typedef struct {
    float x;
    float y;
    float width;
    float height;
    float confidence;
} vision_face_detection_t;

enum {
    VISION_OK = 0,
    VISION_ERR_ARGUMENT = 1,
    VISION_ERR_OPEN_CAMERA = 2,
    VISION_ERR_OPEN_MODEL = 3,
    VISION_ERR_READ_FRAME = 4,
    VISION_ERR_NO_FRAME = 5,
    VISION_ERR_CAPACITY = 6,
    VISION_ERR_NATIVE = 7,
    VISION_PREVIEW_QUIT = 8
};

int vision_open(int camera_index, const char *model_path, int width, int height,
                double fps, vision_handle_t **out, char *error, size_t error_size);
int vision_read(vision_handle_t *handle, char *error, size_t error_size);
int vision_detect(vision_handle_t *handle, vision_face_detection_t *detections,
                  size_t capacity, size_t *count, char *error, size_t error_size);
int vision_preview(vision_handle_t *handle, const vision_face_detection_t *detections,
                   size_t count, char *error, size_t error_size);
void vision_close(vision_handle_t *handle);

#ifdef __cplusplus
}
#endif

#endif
