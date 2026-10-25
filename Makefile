.PHONY: demo live test serve smoke
demo:  ; python3 -m pipeline.build demo
live:  ; python3 -m pipeline.build live
test:  ; npm test
serve: ; python3 -m http.server 8000 --directory web
smoke: ; node scripts/screenshot.mjs docs
