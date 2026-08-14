#!/usr/bin/env python3

import json
import math
import struct
import sys
import zlib


def read_chunks(data):
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("not a PNG file")
    position = 8
    while position + 8 <= len(data):
        length = struct.unpack(">I", data[position:position + 4])[0]
        kind = data[position + 4:position + 8]
        chunk = data[position + 8:position + 8 + length]
        yield kind, chunk
        position += 12 + length


def paeth(a, b, c):
    prediction = a + b - c
    distances = (abs(prediction - a), abs(prediction - b), abs(prediction - c))
    if distances[0] <= distances[1] and distances[0] <= distances[2]:
        return a
    if distances[1] <= distances[2]:
        return b
    return c


def analyze(png_path):
    with open(png_path, "rb") as handle:
        data = handle.read()

    width = height = bit_depth = color_type = interlace = None
    compressed_rows = []
    for kind, chunk in read_chunks(data):
        if kind == b"IHDR":
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(
                ">IIBBBBB", chunk
            )
        elif kind == b"IDAT":
            compressed_rows.append(chunk)
    if width is None:
        raise ValueError("missing PNG IHDR")
    if bit_depth != 8 or interlace != 0 or color_type not in (0, 2, 6):
        raise ValueError(
            f"unsupported PNG format bitDepth={bit_depth} "
            f"colorType={color_type} interlace={interlace}"
        )

    channels = {0: 1, 2: 3, 6: 4}[color_type]
    stride = width * channels
    raw = zlib.decompress(b"".join(compressed_rows))
    rows = []
    position = 0
    previous = bytearray(stride)
    for _ in range(height):
        filter_type = raw[position]
        position += 1
        scan = bytearray(raw[position:position + stride])
        position += stride
        reconstructed = bytearray(stride)
        for index, value in enumerate(scan):
            left = reconstructed[index - channels] if index >= channels else 0
            up = previous[index]
            up_left = previous[index - channels] if index >= channels else 0
            if filter_type == 0:
                reconstructed[index] = value
            elif filter_type == 1:
                reconstructed[index] = (value + left) & 0xFF
            elif filter_type == 2:
                reconstructed[index] = (value + up) & 0xFF
            elif filter_type == 3:
                reconstructed[index] = (value + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                reconstructed[index] = (value + paeth(left, up, up_left)) & 0xFF
            else:
                raise ValueError(f"unsupported PNG filter {filter_type}")
        rows.append(reconstructed)
        previous = reconstructed

    # Sparse native UIs often put their only visible controls close to the
    # left edge or just below the title bar. Keep the lower title-bar margin,
    # but include the full client width and the first few rows of content.
    x0 = 0
    x1 = width
    y0 = int(height * 0.04)
    y1 = max(y0 + 1, int(height * 0.94))
    step_x = max(1, (x1 - x0) // 240)
    step_y = max(1, (y1 - y0) // 180)

    count = dark_count = bright_count = transparent_count = 0
    luminance_sum = luminance_squared_sum = 0.0
    colors = set()
    for y in range(y0, y1, step_y):
        row = rows[y]
        for x in range(x0, x1, step_x):
            offset = x * channels
            if color_type == 0:
                red = green = blue = row[offset]
            else:
                red, green, blue = row[offset:offset + 3]
            alpha = row[offset + 3] if color_type == 6 else 255
            luminance = (0.2126 * red) + (0.7152 * green) + (0.0722 * blue)
            luminance_sum += luminance
            luminance_squared_sum += luminance * luminance
            dark_count += luminance < 18
            bright_count += luminance > 238
            transparent_count += alpha < 16
            colors.add((red >> 4, green >> 4, blue >> 4))
            count += 1

    mean = luminance_sum / count if count else 0.0
    variance = max(0.0, (luminance_squared_sum / count) - (mean * mean)) if count else 0.0
    standard_deviation = math.sqrt(variance)
    dark_ratio = dark_count / count if count else 0.0
    bright_ratio = bright_count / count if count else 0.0
    transparent_ratio = transparent_count / count if count else 0.0
    unique_ratio = len(colors) / count if count else 0.0
    non_bright_count = count - bright_count

    classification = "rendered"
    if transparent_ratio >= 0.50:
        classification = "transparent-window"
    elif dark_ratio >= 0.92:
        classification = "black-window"
    elif dark_count >= 64 or (standard_deviation >= 6.0 and non_bright_count >= 256):
        classification = "rendered"
    elif bright_ratio >= 0.92:
        classification = (
            "partial-render-window"
            if len(colors) >= 8 and non_bright_count >= 32
            else "white-window"
        )
    # A sparse UI can legitimately use very few quantized colors. Only apply
    # the color-count fallback to nearly uniform captures so those UIs are not
    # reported as blank windows.
    elif standard_deviation < 6.0 or (unique_ratio < 0.002 and len(colors) < 8):
        classification = "low-information-window"

    return {
        "path": png_path,
        "width": width,
        "height": height,
        "sampledPixels": count,
        "meanLuminance": round(mean, 2),
        "luminanceStdDev": round(standard_deviation, 2),
        "darkRatio": round(dark_ratio, 4),
        "brightRatio": round(bright_ratio, 4),
        "transparentRatio": round(transparent_ratio, 4),
        "nonBrightPixelCount": non_bright_count,
        "quantizedColorCount": len(colors),
        "uniqueQuantizedColorRatio": round(unique_ratio, 5),
        "classification": classification,
    }


if len(sys.argv) != 3:
    raise SystemExit("usage: analyze-window-image.py <input.png> <output.json>")

result = analyze(sys.argv[1])
with open(sys.argv[2], "w", encoding="utf-8") as handle:
    json.dump(result, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
print(result["classification"])
