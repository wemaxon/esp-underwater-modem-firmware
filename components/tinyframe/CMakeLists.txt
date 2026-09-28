# Vendored upstream sources live in third_party/tinyframe; this component adds
# the project's framing configuration (include/TF_Config.h).
idf_component_register(
    SRCS
        "../../third_party/tinyframe/TinyFrame.c"

    INCLUDE_DIRS
        "include"
        "../../third_party/tinyframe"
)
