DOT      = dot
DIAGRAMS = model-diagram

all: $(DIAGRAMS:%=%.svg)

%.svg: %.dot
	${DOT} $< -Tsvg -o $@
