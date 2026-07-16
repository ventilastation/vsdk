#include "vs2_wire.h"

#include <string.h>

static uint8_t rd_u8(const uint8_t* p) {
    return p[0];
}

static uint16_t rd_u16(const uint8_t* p) {
    return (uint16_t)p[0] | ((uint16_t)p[1] << 8);
}

static uint32_t rd_u32(const uint8_t* p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static int32_t rd_s32(const uint8_t* p) {
    return (int32_t)rd_u32(p);
}

bool vs2_wire_decode_scene(const uint8_t* data, size_t len, vs2_wire_scene_t* out) {
    if (len < 16 || memcmp(data, "VS2\0", 4) != 0) {
        return false;
    }

    uint8_t version = rd_u8(data + 4);
    uint8_t layer_count = rd_u8(data + 5);
    uint8_t sprite_count = rd_u8(data + 6);
    uint8_t tilemap_count = rd_u8(data + 7);
    uint16_t header_size = rd_u16(data + 8);
    uint16_t layer_size = rd_u16(data + 10);
    uint16_t sprite_size = rd_u16(data + 12);
    uint16_t tilemap_size = rd_u16(data + 14);

    if (version != 1 && version != 2) {
        return false;
    }
    if (version < 2) {
        tilemap_count = 0;
        tilemap_size = 0;
    }
    if (layer_count > VS2_MAX_LAYERS || sprite_count > VS2_MAX_SPRITES ||
        tilemap_count > VS2_MAX_TILEMAPS) {
        return false;
    }

    size_t offset = header_size;

    for (int i = 0; i < layer_count; i++) {
        if (offset + layer_size > len) {
            return false;
        }
        const uint8_t* p = data + offset;
        vs2_layer_t* layer = &out->layer_storage[i];
        layer->id = rd_u8(p);
        layer->mode = rd_u8(p + 1);
        layer->flags = rd_u8(p + 2);
        out->layer_ptrs[i] = layer;
        offset += layer_size;
    }

    /* Wire layout "<BBBBBBhhii": layer_id, image, frame, mode, flags,
     * reserved0 (5 uint8 + 1 reserved uint8), reserved1/2 (2 int16, unused),
     * x_fixed, y_fixed (2 int32, Q8 fixed point == vs2_sprite_t.x/.y units
     * directly, no conversion needed). */
    for (int i = 0; i < sprite_count; i++) {
        if (offset + sprite_size > len) {
            return false;
        }
        const uint8_t* p = data + offset;
        vs2_sprite_t* sprite = &out->sprite_storage[i];
        sprite->layer = rd_u8(p);
        sprite->image_strip = rd_u8(p + 1);
        sprite->frame = rd_u8(p + 2);
        sprite->mode = rd_u8(p + 3);
        sprite->flags = rd_u8(p + 4);
        sprite->x = rd_s32(p + 10);
        sprite->y = rd_s32(p + 14);
        out->sprite_ptrs[i] = sprite;
        offset += sprite_size;
    }

    /* Wire layout "<BBBBHHHHHHHHiiI". */
    for (int i = 0; i < tilemap_count; i++) {
        if (offset + tilemap_size > len) {
            return false;
        }
        const uint8_t* p = data + offset;
        vs2_tilemap_t* tilemap = &out->tilemap_storage[i];
        tilemap->layer = rd_u8(p);
        tilemap->image_strip = rd_u8(p + 1);
        tilemap->flags = rd_u8(p + 2);
        tilemap->mode = rd_u8(p + 3);
        tilemap->columns = rd_u16(p + 4);
        tilemap->rows = rd_u16(p + 6);
        tilemap->tile_width = rd_u16(p + 8);
        tilemap->tile_height = rd_u16(p + 10);
        tilemap->viewport_x = rd_u16(p + 12);
        tilemap->viewport_y = rd_u16(p + 14);
        tilemap->viewport_w = rd_u16(p + 16);
        tilemap->viewport_h = rd_u16(p + 18);
        tilemap->x = rd_s32(p + 20);
        tilemap->y = rd_s32(p + 24);
        uint32_t frames_offset = rd_u32(p + 28);
        uint32_t cells = (uint32_t)tilemap->columns * (uint32_t)tilemap->rows;
        if ((size_t)frames_offset + cells > len) {
            return false;
        }
        tilemap->frames = data + frames_offset;
        tilemap->frames_len = cells;
        out->tilemap_ptrs[i] = tilemap;
        offset += tilemap_size;
    }

    out->scene.layer_count = layer_count;
    out->scene.sprite_count = sprite_count;
    out->scene.tilemap_count = tilemap_count;
    out->scene.layers = out->layer_ptrs;
    out->scene.sprites = out->sprite_ptrs;
    out->scene.tilemaps = out->tilemap_ptrs;
    return true;
}
