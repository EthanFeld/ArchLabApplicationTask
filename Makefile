PYTHON ?= python

.PHONY: submit-check test-brightness test-persistent test-lut smoke benchmark scaling persistent-scaling

submit-check:
	$(PYTHON) -m pytest -q

test-brightness:
	$(PYTHON) tools/run_test.py test.test_brightness_satadd --build-name satadd_test --parameter DATA_MEM_ADDR_BITS=16 --parameter DATA_MEM_DATA_BITS=16 --parameter THREAD_COUNT_BITS=16

test-persistent:
	$(PYTHON) tools/run_test.py test.test_brightness_persistent --build-name persistent_test --parameter DATA_MEM_ADDR_BITS=16 --parameter DATA_MEM_DATA_BITS=16 --parameter THREAD_COUNT_BITS=16

test-lut:
	$(PYTHON) tools/run_test.py test.test_adaptive_gamma_lut --build-name lut_test --parameter DATA_MEM_ADDR_BITS=16 --parameter DATA_MEM_DATA_BITS=16 --parameter THREAD_COUNT_BITS=16

smoke:
	$(PYTHON) tools/run_brightness.py inputs/green_parrot_64.png results/make_smoke_green_parrot_64_bright.png --stats-json results/make_smoke_green_parrot_64_stats.json --brightness 48

benchmark:
	$(PYTHON) tools/benchmark_brightness.py --inputs inputs/green_parrot_64.png inputs/red_flower_64.png inputs/green_parrot_128.png inputs/red_flower_128.png --results-dir results --brightness 48

scaling:
	$(PYTHON) tools/benchmark_size_scaling.py --sizes 32 64 96 128 160 192 --results-dir results --generated-dir results/scaling_inputs --brightness 48

persistent-scaling:
	$(PYTHON) tools/benchmark_size_scaling.py --mode brightness-persistent --sizes 32 64 96 128 160 192 --results-dir results --generated-dir results/scaling_inputs --brightness 48
