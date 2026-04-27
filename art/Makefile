MAGIC_ARGS = -rcfile $(PDK_ROOT)/sky130A/libs.tech/magic/sky130A.magicrc -noconsole

chip_art.lef: chip_art.gds
	(echo "gds read chip_art.gds"; echo "load chip_art"; echo "lef write chip_art.lef"; echo "quit -noprompt") | magic $(MAGIC_ARGS) -dnull

chip_art.gds: make_gds.py chip_art.png
	python make_gds.py -v -i chip_art.png -c chip_art -o chip_art.gds

run_magic:
	magic $(MAGIC_ARGS)

.PHONY: run_magic
