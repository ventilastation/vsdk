from PIL import Image
import os
import math
from PIL import ImageDraw


DEBUG = True
ANGLES = [0, 45, 65]
folder = os.path.dirname(__file__)

all_frames = {}

for angle in ANGLES:
    src_path = os.path.join(folder, f"dedo-src{angle}.gif")

    with Image.open(src_path) as im:
        frames = []
        all_frames[angle] = frames
        try:
            while True:
                frame = im.copy().convert("RGBA")
                frames.append(frame)
                im.seek(im.tell() + 1)
        except EOFError:
            pass


max_height = max(frame.size[1] for frames in all_frames.values() for frame in frames)
max_width = max(frame.size[0] for frames in all_frames.values() for frame in frames)
slot_width = max(frames[0].size[0] + int(2 * max_height * abs(math.tan(math.radians(angle)))) for angle, frames in all_frames.items()) 
print("Max height:", max_height)
print("Max width:", max_width)
print("Slot width:", slot_width)

for angle, frames in all_frames.items():
    num_frames = len(frames)
    angle_rad = math.radians(angle)
    dx_per_pixel = math.tan(angle_rad)
    max_shift_x = int(max_height * abs(dx_per_pixel))
    out_w = max_width + max_shift_x
    out_h = max_height
    total_steps = max_height + num_frames - 1
    out_img = Image.new("RGBA", (slot_width * total_steps, out_h), (0, 0, 0, 0))
    out_img_neg = Image.new("RGBA", (slot_width * total_steps, out_h), (0, 0, 0, 0))
    base_x = 0
    for step in range(total_steps):
        visible = min(step + 1, max_height)
        frame_idx = step % num_frames
        frame = frames[frame_idx]
        frame_w, frame_h = frame.size
        frame_canvas = Image.new("RGBA", (slot_width, out_h), (0, 0, 0, 0))
        crop_box = (0, 0, frame_w, visible)
        part = frame.crop(crop_box)
        y_offset = out_h - visible

        mid_x = slot_width // 2
        if angle > 0:
            x_offset = mid_x - frame_w + int((visible - out_h) * dx_per_pixel)
        else: 
            x_offset = (slot_width - frame_w) // 2

        if DEBUG:
            draw = ImageDraw.Draw(frame_canvas)
            draw.line([(mid_x, 0), (mid_x, out_h)], fill=(255, 0, 0, 255), width=1)
            draw.line([(0, 0), (0, out_h)], fill=(0, 0, 255, 255), width=1)
            print("mid_x:", mid_x, "step:", step, "x_offset:", x_offset)

        frame_canvas.alpha_composite(part, (x_offset, y_offset))
        out_img.paste(frame_canvas, (step * slot_width, 0), frame_canvas)



    dst_path = f"../dedo-frames{angle}.png"
    out_img.save(dst_path)

    if angle != 0:
        for step in range(total_steps):
            box = (step * slot_width, 0, (step + 1) * slot_width, out_h)
            frame_region = out_img.crop(box)
            flipped = frame_region.transpose(Image.FLIP_LEFT_RIGHT)
            out_img_neg.paste(flipped, (step * slot_width, 0), flipped)
        
        out_img_neg.save(dst_path.replace(".png", "-neg.png"))
