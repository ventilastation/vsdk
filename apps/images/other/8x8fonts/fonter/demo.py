from PIL import Image

# Open the source PNG file
source_path = "IBM_VGA_8x8.png"  # Change this to your PNG file path
src_img = Image.open(source_path)
src_width, src_height = src_img.size

# Create an empty image of 2048x8 pixels, RGBA mode
output_width = 256*8
output_height = 8
output_img = Image.new("RGBA", (output_width, output_height), (0, 0, 0, 0))

num_sections = src_height // 9

# Copy each 8-pixel-high section and paste it horizontally in the output image
for i in range(num_sections):
    for j in range(16):
        box = (j*9+1, i * 9, j*9+9, (i + 1) * 9)
        char = src_img.crop(box)
        paste_x = i * 128 + j * 8
        output_img.paste(char, (paste_x, 0))

# Save the result
output_img.save("output.png")
