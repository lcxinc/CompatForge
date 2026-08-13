extends Control

var rendered_frames := 0
var capture_started := false


func _process(_delta: float) -> void:
	rendered_frames += 1
	if rendered_frames >= 12 and not capture_started:
		capture_started = true
		capture_frame()


func capture_frame() -> void:
	await RenderingServer.frame_post_draw
	var image := get_viewport().get_texture().get_image()
	var output_path := ProjectSettings.globalize_path("res://godot-vulkan-smoke.png")
	var save_error := image.save_png(output_path)
	var left_pixel := image.get_pixel(96, 420)
	var right_pixel := image.get_pixel(864, 420)
	var color_delta: float = (
		abs(left_pixel.r - right_pixel.r)
		+ abs(left_pixel.g - right_pixel.g)
		+ abs(left_pixel.b - right_pixel.b)
	)

	print(
		"MACWIN_GODOT_FRAME width=", image.get_width(),
		" height=", image.get_height(),
		" color_delta=", color_delta,
		" save_error=", save_error
	)
	if (
		save_error == OK
		and image.get_width() == 960
		and image.get_height() == 540
		and color_delta > 0.25
	):
		print("MACWIN_GODOT_VULKAN=PASS")
		get_tree().quit(0)
	else:
		printerr("MACWIN_GODOT_VULKAN=FAIL")
		get_tree().quit(1)
