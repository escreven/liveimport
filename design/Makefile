DOT      = dot
DIAGRAMS = model-diagram

all: $(DIAGRAMS:%=%.svg)

%.svg: %.gv
	${DOT} $< -Tsvg -o $@
