# Create an INTERFACE library for native app handoff hooks.
add_library(usermod_native_apps INTERFACE)

# Add our source files to the lib.
target_sources(usermod_native_apps INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/native_apps.c
)

# Add the current directory as an include directory.
target_include_directories(usermod_native_apps INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}
)

# Link our INTERFACE library to the usermod target.
target_link_libraries(usermod INTERFACE usermod_native_apps)
