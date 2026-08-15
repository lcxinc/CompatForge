cmake_minimum_required(VERSION 3.24)

project(CompatForgeDesktop VERSION 0.11.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)
set(CMAKE_AUTOUIC ON)

find_package(Qt6 6.8 REQUIRED COMPONENTS Core Gui Qml Quick QuickControls2 Test)
qt_policy(SET QTP0001 NEW)
qt_policy(SET QTP0004 NEW)

set(COMPATFORGE_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../..")
set(COMPATFORGE_CARGO_TARGET "${CMAKE_BINARY_DIR}/cargo-target")
if(APPLE)
  set(COMPATFORGE_FFI_LIBRARY "${COMPATFORGE_CARGO_TARGET}/release/libcompatforge_ffi.dylib")
elseif(WIN32)
  set(COMPATFORGE_FFI_LIBRARY "${COMPATFORGE_CARGO_TARGET}/release/compatforge_ffi.dll")
else()
  set(COMPATFORGE_FFI_LIBRARY "${COMPATFORGE_CARGO_TARGET}/release/libcompatforge_ffi.so")
endif()

add_custom_command(
  OUTPUT "${COMPATFORGE_FFI_LIBRARY}"
  COMMAND ${CMAKE_COMMAND} -E env CARGO_TARGET_DIR=${COMPATFORGE_CARGO_TARGET}
          cargo build --release --locked --package compatforge-ffi --manifest-path "${COMPATFORGE_ROOT}/Cargo.toml"
  WORKING_DIRECTORY "${COMPATFORGE_ROOT}"
  COMMENT "Building CompatForge Rust FFI"
  VERBATIM
)
add_custom_target(compatforge-ffi-build DEPENDS "${COMPATFORGE_FFI_LIBRARY}")

add_library(compatforge-ffi SHARED IMPORTED GLOBAL)
set_target_properties(compatforge-ffi PROPERTIES
  IMPORTED_LOCATION "${COMPATFORGE_FFI_LIBRARY}"
  INTERFACE_INCLUDE_DIRECTORIES "${COMPATFORGE_ROOT}/crates/compatforge-ffi/include"
)
add_dependencies(compatforge-ffi compatforge-ffi-build)

qt_add_executable(CompatForge
  src/main.cpp
  src/compatforgecontroller.cpp
  src/compatforgecontroller.h
)
add_dependencies(CompatForge compatforge-ffi-build)
target_link_libraries(CompatForge PRIVATE
  Qt6::Core Qt6::Gui Qt6::Qml Qt6::Quick Qt6::QuickControls2 compatforge-ffi
)
target_include_directories(CompatForge PRIVATE
  "${COMPATFORGE_ROOT}/crates/compatforge-ffi/include"
)

qt_add_qml_module(CompatForge
  URI CompatForge.Desktop
  VERSION 1.0
  QML_FILES qml/Main.qml
)

if(APPLE)
  set_target_properties(CompatForge PROPERTIES
    MACOSX_BUNDLE TRUE
    MACOSX_BUNDLE_GUI_IDENTIFIER "dev.compatforge.desktop"
    MACOSX_BUNDLE_BUNDLE_NAME "CompatForge"
    BUILD_RPATH "@loader_path/../Frameworks;@executable_path/../Frameworks"
    INSTALL_RPATH "@loader_path/../Frameworks;@executable_path/../Frameworks"
  )
elseif(UNIX)
  set_target_properties(CompatForge PROPERTIES BUILD_RPATH "${COMPATFORGE_CARGO_TARGET}/release")
endif()

if(APPLE)
  add_custom_command(TARGET CompatForge POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E make_directory "$<TARGET_BUNDLE_DIR:CompatForge>/Contents/Frameworks"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${COMPATFORGE_FFI_LIBRARY}"
            "$<TARGET_BUNDLE_DIR:CompatForge>/Contents/Frameworks/libcompatforge_ffi.dylib"
    COMMAND install_name_tool -id "@rpath/libcompatforge_ffi.dylib"
            "$<TARGET_BUNDLE_DIR:CompatForge>/Contents/Frameworks/libcompatforge_ffi.dylib"
    COMMAND install_name_tool -change "${COMPATFORGE_FFI_LIBRARY}"
            "@rpath/libcompatforge_ffi.dylib" "$<TARGET_FILE:CompatForge>"
    COMMAND install_name_tool -change "${COMPATFORGE_CARGO_TARGET}/release/deps/libcompatforge_ffi.dylib"
            "@rpath/libcompatforge_ffi.dylib" "$<TARGET_FILE:CompatForge>"
    VERBATIM
  )
endif()

enable_testing()
qt_add_executable(CompatForgeQtTest
  tests/tst_compatforgecontroller.cpp
  src/compatforgecontroller.cpp
)
target_link_libraries(CompatForgeQtTest PRIVATE Qt6::Core Qt6::Test compatforge-ffi)
add_dependencies(CompatForgeQtTest compatforge-ffi-build)
target_include_directories(CompatForgeQtTest PRIVATE
  "${CMAKE_CURRENT_SOURCE_DIR}/src"
  "${COMPATFORGE_ROOT}/crates/compatforge-ffi/include"
)
add_test(NAME CompatForgeQtTest COMMAND CompatForgeQtTest)
set_tests_properties(CompatForgeQtTest PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen")

install(TARGETS CompatForge BUNDLE DESTINATION . RUNTIME DESTINATION bin)
