.PHONY: lint test build-deb

lint:
	python3 -m py_compile lib/local-jev/local_jev_runtime.py
	shellcheck bin/local-jev scripts/build-deb.sh scripts/try-kev.sh debian/postinst
	python3 scripts/check-text.py

test:
	python3 tests/test_runtime.py

build-deb:
	bash scripts/build-deb.sh
