.PHONY: check-gpu

check-gpu:
	docker exec -it tikplayer_v2 ls -l /dev/dri
	docker exec -it tikplayer_v2 ffmpeg -hide_banner -hwaccels
	docker exec -it tikplayer_v2 ffmpeg -hide_banner -encoders | grep -E "vaapi|qsv" || true
	docker exec -it tikplayer_v2 vainfo || true
