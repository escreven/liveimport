DOT       = dot
DIAGRAMS  = model-diagram
PYTHON   := $(if $(findstring CYGWIN,$(UNAME)),py,python3)

all: $(DIAGRAMS:%=%.svg)

%.svg: %.py
	${PYTHON} $<
