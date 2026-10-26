CXX ?= g++
CXXFLAGS ?= -O2 -g -Wall -Wextra -std=c++17
CPPFLAGS += $(shell pkg-config --cflags Qt6Widgets qtermwidget6)
LDLIBS += $(shell pkg-config --libs Qt6Widgets qtermwidget6)

j701f-gui: main.cpp latency-test.h
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -o $@ $< $(LDLIBS)

clean:
	rm -f j701f-gui
