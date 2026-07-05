.PHONY: all test clean

all:
	PYTHONPATH=src python -m ptbase.cli all

test:
	pytest

clean:
	find data/intermediate reports -type f -delete
