#include <stdint.h>
#include <string.h>

#include "py/obj.h"
#include "py/runtime.h"

#include "gpu.h"

#define VS2_FLAG_VISIBLE 0x01
#define VS2_NO_LAYER 255

typedef struct {
    mp_obj_base_t base;
    uint8_t slot;
    vs2_layer_t layer;
} vs2_layer_obj_t;

typedef struct {
    mp_obj_base_t base;
    uint8_t slot;
    vs2_sprite_t sprite;
} vs2_sprite_obj_t;

const mp_obj_type_t vs2_layer_type;
const mp_obj_type_t vs2_sprite_type;

static const vs2_layer_t* vs2_layer_records[VS2_MAX_LAYERS];
static const vs2_sprite_t* vs2_sprite_records[VS2_MAX_SPRITES];

bool vs2_render_active = false;
vs2_scene_t vs2_active_scene = {
    .layer_count = 0,
    .sprite_count = 0,
    .layers = vs2_layer_records,
    .sprites = vs2_sprite_records,
};

static uint8_t alloc_layer_slot(const vs2_layer_t* layer) {
    for (uint8_t slot = 0; slot < VS2_MAX_LAYERS; slot++) {
        if (vs2_layer_records[slot] == NULL) {
            vs2_layer_records[slot] = layer;
            if (slot >= vs2_active_scene.layer_count) {
                vs2_active_scene.layer_count = slot + 1;
            }
            return slot;
        }
    }
    mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("too many vs2 layers"));
    return 0;
}

static uint8_t alloc_sprite_slot(const vs2_sprite_t* sprite) {
    for (uint8_t slot = 0; slot < VS2_MAX_SPRITES; slot++) {
        if (vs2_sprite_records[slot] == NULL) {
            vs2_sprite_records[slot] = sprite;
            if (slot >= vs2_active_scene.sprite_count) {
                vs2_active_scene.sprite_count = slot + 1;
            }
            return slot;
        }
    }
    mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("too many vs2 sprites"));
    return 0;
}

static vs2_sprite_obj_t* to_vs2_sprite(mp_obj_t obj) {
    if (!mp_obj_is_type(obj, &vs2_sprite_type)) {
        mp_raise_TypeError(MP_ERROR_TEXT("expected vs2 Sprite"));
    }
    return MP_OBJ_TO_PTR(obj);
}

static vs2_layer_obj_t* to_vs2_layer(mp_obj_t obj) {
    if (!mp_obj_is_type(obj, &vs2_layer_type)) {
        mp_raise_TypeError(MP_ERROR_TEXT("expected vs2 Layer"));
    }
    return MP_OBJ_TO_PTR(obj);
}

static mp_obj_t vs2_reset_scene(void) {
    vs2_render_active = false;
    memset(vs2_layer_records, 0, sizeof(vs2_layer_records));
    memset(vs2_sprite_records, 0, sizeof(vs2_sprite_records));
    vs2_active_scene.layer_count = 0;
    vs2_active_scene.sprite_count = 0;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(vs2_reset_scene_obj, vs2_reset_scene);

static mp_obj_t vs2_set_active(mp_obj_t active) {
    vs2_render_active = mp_obj_is_true(active);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(vs2_set_active_obj, vs2_set_active);

static void vs2_layer_print(const mp_print_t *print, mp_obj_t self_in, mp_print_kind_t kind) {
    vs2_layer_obj_t *self = MP_OBJ_TO_PTR(self_in);
    mp_printf(print, "<vs2.Layer slot=%d mode=%d>", self->slot, self->layer.mode);
}

static mp_obj_t vs2_layer_make_new(const mp_obj_type_t *type, size_t n_args, size_t n_kw, const mp_obj_t *all_args) {
    enum { ARG_mode, ARG_visible };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_mode, MP_ARG_INT, {.u_int = 1} },
        { MP_QSTR_visible, MP_ARG_BOOL, {.u_bool = true} },
    };

    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all_kw_array(n_args, n_kw, all_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    vs2_layer_obj_t *self = m_new_obj(vs2_layer_obj_t);
    self->base.type = type;
    self->layer.id = 0;
    self->layer.mode = args[ARG_mode].u_int;
    self->layer.flags = args[ARG_visible].u_bool ? VS2_FLAG_VISIBLE : 0;
    self->slot = alloc_layer_slot(&self->layer);
    self->layer.id = self->slot;
    return MP_OBJ_FROM_PTR(self);
}

static mp_obj_t vs2_layer_set_mode(mp_obj_t self_in, mp_obj_t mode_in) {
    vs2_layer_obj_t *self = MP_OBJ_TO_PTR(self_in);
    self->layer.mode = mp_obj_get_int(mode_in);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(vs2_layer_set_mode_obj, vs2_layer_set_mode);

static mp_obj_t vs2_layer_set_visible(mp_obj_t self_in, mp_obj_t visible_in) {
    vs2_layer_obj_t *self = MP_OBJ_TO_PTR(self_in);
    if (mp_obj_is_true(visible_in)) {
        self->layer.flags |= VS2_FLAG_VISIBLE;
    } else {
        self->layer.flags &= ~VS2_FLAG_VISIBLE;
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(vs2_layer_set_visible_obj, vs2_layer_set_visible);

static const mp_rom_map_elem_t vs2_layer_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR_set_mode), MP_ROM_PTR(&vs2_layer_set_mode_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_visible), MP_ROM_PTR(&vs2_layer_set_visible_obj) },
};
static MP_DEFINE_CONST_DICT(vs2_layer_locals_dict, vs2_layer_locals_dict_table);

MP_DEFINE_CONST_OBJ_TYPE(
    vs2_layer_type,
    MP_QSTR_Layer,
    MP_TYPE_FLAG_NONE,
    print, vs2_layer_print,
    make_new, vs2_layer_make_new,
    locals_dict, &vs2_layer_locals_dict
);

static void vs2_sprite_print(const mp_print_t *print, mp_obj_t self_in, mp_print_kind_t kind) {
    vs2_sprite_obj_t *self = MP_OBJ_TO_PTR(self_in);
    mp_printf(print, "<vs2.Sprite slot=%d strip=%d frame=%d>", self->slot, self->sprite.image_strip, self->sprite.frame);
}

static mp_obj_t vs2_sprite_make_new(const mp_obj_type_t *type, size_t n_args, size_t n_kw, const mp_obj_t *all_args) {
    enum { ARG_replacing };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_replacing, MP_ARG_OBJ, {.u_obj = MP_OBJ_NULL} },
    };

    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all_kw_array(n_args, n_kw, all_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    vs2_sprite_obj_t *self = m_new_obj(vs2_sprite_obj_t);
    self->base.type = type;
    self->sprite.layer = VS2_NO_LAYER;
    self->sprite.image_strip = 0;
    self->sprite.frame = 255;
    self->sprite.mode = 1;
    self->sprite.flags = 0;
    self->sprite.x = 0;
    self->sprite.y = 0;

    mp_obj_t replacing = args[ARG_replacing].u_obj;
    if (replacing == MP_OBJ_NULL) {
        self->slot = alloc_sprite_slot(&self->sprite);
    } else {
        vs2_sprite_obj_t *replacing_sprite = to_vs2_sprite(replacing);
        self->slot = replacing_sprite->slot;
        vs2_sprite_records[self->slot] = &self->sprite;
    }
    return MP_OBJ_FROM_PTR(self);
}

static mp_obj_t vs2_sprite_disable(mp_obj_t self_in) {
    vs2_sprite_obj_t *self = MP_OBJ_TO_PTR(self_in);
    self->sprite.flags &= ~VS2_FLAG_VISIBLE;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(vs2_sprite_disable_obj, vs2_sprite_disable);

static mp_obj_t vs2_sprite_width(mp_obj_t self_in) {
    vs2_sprite_obj_t *self = MP_OBJ_TO_PTR(self_in);
    const ImageStrip* strip = image_stripes[self->sprite.image_strip];
    if ((uintptr_t)strip < 1000) {
        return mp_obj_new_int(0);
    }
    int width = strip->frame_width;
    if (width == 255) width++;
    return mp_obj_new_int(width);
}
static MP_DEFINE_CONST_FUN_OBJ_1(vs2_sprite_width_obj, vs2_sprite_width);

static mp_obj_t vs2_sprite_height(mp_obj_t self_in) {
    vs2_sprite_obj_t *self = MP_OBJ_TO_PTR(self_in);
    const ImageStrip* strip = image_stripes[self->sprite.image_strip];
    if ((uintptr_t)strip < 1000) {
        return mp_obj_new_int(0);
    }
    return mp_obj_new_int(strip->frame_height);
}
static MP_DEFINE_CONST_FUN_OBJ_1(vs2_sprite_height_obj, vs2_sprite_height);

static mp_obj_t vs2_sprite_set_x_fixed(mp_obj_t self_in, mp_obj_t value_in) {
    vs2_sprite_obj_t *self = MP_OBJ_TO_PTR(self_in);
    self->sprite.x = mp_obj_get_int(value_in);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(vs2_sprite_set_x_fixed_obj, vs2_sprite_set_x_fixed);

static mp_obj_t vs2_sprite_set_y_fixed(mp_obj_t self_in, mp_obj_t value_in) {
    vs2_sprite_obj_t *self = MP_OBJ_TO_PTR(self_in);
    self->sprite.y = mp_obj_get_int(value_in);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(vs2_sprite_set_y_fixed_obj, vs2_sprite_set_y_fixed);

static mp_obj_t vs2_sprite_set_x(mp_obj_t self_in, mp_obj_t value_in) {
    vs2_sprite_obj_t *self = MP_OBJ_TO_PTR(self_in);
    self->sprite.x = mp_obj_get_int(value_in) * 256;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(vs2_sprite_set_x_obj, vs2_sprite_set_x);

static mp_obj_t vs2_sprite_set_y(mp_obj_t self_in, mp_obj_t value_in) {
    vs2_sprite_obj_t *self = MP_OBJ_TO_PTR(self_in);
    self->sprite.y = mp_obj_get_int(value_in) * 256;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(vs2_sprite_set_y_obj, vs2_sprite_set_y);

static mp_obj_t vs2_sprite_set_strip(mp_obj_t self_in, mp_obj_t value_in) {
    vs2_sprite_obj_t *self = MP_OBJ_TO_PTR(self_in);
    self->sprite.image_strip = mp_obj_get_int(value_in);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(vs2_sprite_set_strip_obj, vs2_sprite_set_strip);

static mp_obj_t vs2_sprite_set_frame(mp_obj_t self_in, mp_obj_t value_in) {
    vs2_sprite_obj_t *self = MP_OBJ_TO_PTR(self_in);
    self->sprite.frame = mp_obj_get_int(value_in);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(vs2_sprite_set_frame_obj, vs2_sprite_set_frame);

static mp_obj_t vs2_sprite_set_perspective(mp_obj_t self_in, mp_obj_t value_in) {
    vs2_sprite_obj_t *self = MP_OBJ_TO_PTR(self_in);
    self->sprite.mode = mp_obj_get_int(value_in);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(vs2_sprite_set_perspective_obj, vs2_sprite_set_perspective);

static mp_obj_t vs2_sprite_set_flags(mp_obj_t self_in, mp_obj_t flags_in) {
    vs2_sprite_obj_t *self = MP_OBJ_TO_PTR(self_in);
    self->sprite.flags = mp_obj_get_int(flags_in);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(vs2_sprite_set_flags_obj, vs2_sprite_set_flags);

static mp_obj_t vs2_sprite_set_layer(mp_obj_t self_in, mp_obj_t layer_in) {
    vs2_sprite_obj_t *self = MP_OBJ_TO_PTR(self_in);
    if (layer_in == mp_const_none) {
        self->sprite.layer = VS2_NO_LAYER;
    } else {
        vs2_layer_obj_t *layer = to_vs2_layer(layer_in);
        self->sprite.layer = layer->slot;
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(vs2_sprite_set_layer_obj, vs2_sprite_set_layer);

static const mp_rom_map_elem_t vs2_sprite_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR_disable), MP_ROM_PTR(&vs2_sprite_disable_obj) },
    { MP_ROM_QSTR(MP_QSTR_width), MP_ROM_PTR(&vs2_sprite_width_obj) },
    { MP_ROM_QSTR(MP_QSTR_height), MP_ROM_PTR(&vs2_sprite_height_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_x), MP_ROM_PTR(&vs2_sprite_set_x_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_y), MP_ROM_PTR(&vs2_sprite_set_y_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_x_fixed), MP_ROM_PTR(&vs2_sprite_set_x_fixed_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_y_fixed), MP_ROM_PTR(&vs2_sprite_set_y_fixed_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_strip), MP_ROM_PTR(&vs2_sprite_set_strip_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_frame), MP_ROM_PTR(&vs2_sprite_set_frame_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_perspective), MP_ROM_PTR(&vs2_sprite_set_perspective_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_flags), MP_ROM_PTR(&vs2_sprite_set_flags_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_layer), MP_ROM_PTR(&vs2_sprite_set_layer_obj) },
};
static MP_DEFINE_CONST_DICT(vs2_sprite_locals_dict, vs2_sprite_locals_dict_table);

MP_DEFINE_CONST_OBJ_TYPE(
    vs2_sprite_type,
    MP_QSTR_Sprite,
    MP_TYPE_FLAG_NONE,
    print, vs2_sprite_print,
    make_new, vs2_sprite_make_new,
    locals_dict, &vs2_sprite_locals_dict
);

static const mp_rom_map_elem_t vs2_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_vshw_vs2) },
    { MP_ROM_QSTR(MP_QSTR_Layer), MP_ROM_PTR(&vs2_layer_type) },
    { MP_ROM_QSTR(MP_QSTR_Sprite), MP_ROM_PTR(&vs2_sprite_type) },
    { MP_ROM_QSTR(MP_QSTR_reset_scene), MP_ROM_PTR(&vs2_reset_scene_obj) },
    { MP_ROM_QSTR(MP_QSTR_reset_sprites), MP_ROM_PTR(&vs2_reset_scene_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_active), MP_ROM_PTR(&vs2_set_active_obj) },
};

static MP_DEFINE_CONST_DICT(mp_module_vs2_globals, vs2_globals_table);

const mp_obj_module_t mp_module_vshw_vs2 = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t*)&mp_module_vs2_globals,
};

MP_REGISTER_MODULE(MP_QSTR_vshw_vs2, mp_module_vshw_vs2);
