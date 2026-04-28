# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2024 Uri Shaked

import gdspy
import sys
from PIL import Image

PNG_NAME = "chip_art.png"
CELL_NAME = "chip_art"
GDS_NAME = "chip_art.gds"

BOUNDARY_LAYERS = [
    (235, 4), # prBndry, boundary
    (62, 24), # cmm1, waffle-drop
    (105, 52), # cmm2, waffle-drop
    (107, 24), # cmm3, waffle-drop
    (112, 4), # cmm4, waffle-drop
    (117, 4), # cmm5, waffle-drop
]
PIXEL_LAYERS = [
    (68, 20), # met1, drawing
    (69, 20), # met2, drawing
    #(70, 20), # met3, drawing
    # (71, 20), # met4, drawing
]
PIXEL_SIZE = 0.28 # um
VERBOSITY = 1
MET1_ONLY_MAX = 200
BOTH_LAYERS_MAX = 100


def run_drc(bitmap, layer_name):
    diagonals = 0
    lone_pixels = 0
    drc_errors = 0

    for y in range(1, len(bitmap)):
        for x in range(1, len(bitmap[y])):
            if (bitmap[y - 1][x - 1] == bitmap[y][x] and
                bitmap[y - 1][x] == bitmap[y][x - 1] and
                bitmap[y - 1][x] != bitmap[y][x]):
                if VERBOSITY > 1:
                    print('[DRC:%s] Diagonally touching pixels at %d,%d' % (layer_name, x, y))
                diagonals += 1
                drc_errors += 1

    for y in range(len(bitmap)):
        for x in range(len(bitmap[y])):
            if (bitmap[y][x] != (y > 0 and bitmap[y - 1][x]) and
                bitmap[y][x] != (y + 1 < len(bitmap) and bitmap[y + 1][x]) and
                bitmap[y][x] != (x > 0 and bitmap[y][x - 1]) and
                bitmap[y][x] != (x + 1 < len(bitmap[y]) and bitmap[y][x + 1])):
                if VERBOSITY > 1:
                    print('[DRC:%s] Lone pixel at %d,%d' % (layer_name, x, y))
                lone_pixels += 1
                drc_errors += 1

    if drc_errors:
        print('Warning: %d DRC issues encountered on %s (%d diagonals, %d lone pixels)' %
              (drc_errors, layer_name, diagonals, lone_pixels))

# Process arguments
args = sys.argv[1:]
while args:
    arg = args.pop(0)
    if arg == '-q':
        VERBOSITY = 0
    elif arg == '-v':
        VERBOSITY = 2
    elif arg == '-u' and args:
        PIXEL_SIZE = float(args.pop(0))
    elif arg == '-i' and args:
        PNG_NAME = args.pop(0)
    elif arg == '-c' and args:
        CELL_NAME = args.pop(0)
    elif arg == '-o' and args:
        GDS_NAME = args.pop(0)
    else:
        print('Unknown argument: %s' % arg)
        exit(1)

# Open the image
img = Image.open(PNG_NAME)
if VERBOSITY > 0:
    print('Input image size: %dpx x %dpx' % (img.width, img.height))

# Convert the image to grayscale
img = img.convert("L")

pixel_values = [[img.getpixel((x, y))
                 for x in range(img.width)]
                for y in range(img.height)]

layer_bitmaps = [
    [[pixel_values[y][x] < MET1_ONLY_MAX
      for x in range(img.width)]
     for y in range(img.height)],
    [[pixel_values[y][x] < BOTH_LAYERS_MAX
      for x in range(img.width)]
     for y in range(img.height)],
]

for layer_name, bitmap in enumerate(layer_bitmaps):
    run_drc(bitmap, layer_name)

layout = gdspy.Cell(CELL_NAME)
size = (img.width * PIXEL_SIZE, img.height * PIXEL_SIZE)
if VERBOSITY > 0:
    print('Output GDS size: %gum x %gum' % size)

for layer, datatype in BOUNDARY_LAYERS:
    layout.add(
        gdspy.Rectangle((0, 0), size,
                        layer=layer, datatype=datatype))
for (layer, datatype), bitmap in zip(PIXEL_LAYERS, layer_bitmaps):
    for y in range(img.height):
        for x in range(img.width):
            if bitmap[y][x]:
                # Adjust y-coordinate to flip the image vertically
                flipped_y = img.height - y - 1
                layout.add(
                    gdspy.Rectangle((x * PIXEL_SIZE, flipped_y * PIXEL_SIZE),
                                    ((x + 1) * PIXEL_SIZE, (flipped_y + 1) * PIXEL_SIZE),
                                    layer=layer, datatype=datatype))

# Save the layout to a file
gdspy.write_gds(GDS_NAME)
