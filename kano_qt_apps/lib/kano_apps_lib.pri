include(kano_apps_deps.pri)

LIBS += -L$$PWD
QMAKE_LFLAGS += -lkano_apps

load(kano_run)

LIB_DIRS += $$PWD
