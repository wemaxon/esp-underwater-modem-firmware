# Host-side unit tests for firmware modules that have no ESP-IDF dependencies.
#
#   cmake -S test/host -B build/host
#   cmake --build build/host --config Debug
#   ctest --test-dir build/host -C Debug --output-on-failure

cmake_minimum_required(VERSION 3.22)
project(firmware_host_tests C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(ROOT ${CMAKE_CURRENT_SOURCE_DIR}/../..)

if(MSVC)
    set(STRICT_WARNINGS /W4 /WX)
else()
    set(STRICT_WARNINGS -Wall -Wextra -Werror)
endif()

enable_testing()

add_executable(test_edge_decoder test_edge_decoder.c
    ${ROOT}/components/edge_capture/edge_decoder.c)
target_include_directories(test_edge_decoder PRIVATE
    ${ROOT}/components/edge_capture/include)

add_executable(test_tuss4470_frame test_tuss4470_frame.c
    ${ROOT}/components/tuss4470/tuss4470_frame.c)
target_include_directories(test_tuss4470_frame PRIVATE
    ${ROOT}/components/tuss4470/private_include)

# Third-party code, built without the strict warning flags.
add_library(tinyframe STATIC ${ROOT}/third_party/tinyframe/TinyFrame.c)
target_include_directories(tinyframe PUBLIC
    ${ROOT}/components/tinyframe/include
    ${ROOT}/third_party/tinyframe)

add_executable(test_tf_protocol test_tf_protocol.c
    ${ROOT}/main/tf_protocol.c)
target_include_directories(test_tf_protocol PRIVATE
    ${ROOT}/main
    ${ROOT}/components/edge_capture/include
    ${ROOT}/components/tuss4470/include)

add_executable(test_tuss4470_waveform test_tuss4470_waveform.c
    ${ROOT}/components/tuss4470/tuss4470_waveform.c)
target_include_directories(test_tuss4470_waveform PRIVATE
    ${ROOT}/components/tuss4470/include)
target_link_libraries(test_tf_protocol PRIVATE tinyframe)

foreach(test test_edge_decoder test_tuss4470_frame test_tf_protocol test_tuss4470_waveform)
    target_compile_options(${test} PRIVATE ${STRICT_WARNINGS})
endforeach()

add_test(NAME edge_decoder COMMAND test_edge_decoder)
add_test(NAME tuss4470_frame COMMAND test_tuss4470_frame)
add_test(NAME tf_protocol COMMAND test_tf_protocol)
add_test(NAME tuss4470_waveform COMMAND test_tuss4470_waveform)
