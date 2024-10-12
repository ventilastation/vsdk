# Create an INTERFACE library for our C module.
add_library(usermod_povdisplay INTERFACE)

# Add our source files to the lib
target_sources(usermod_povdisplay INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/povdisplay.c
    ${CMAKE_CURRENT_LIST_DIR}/gpu.c
    ${CMAKE_CURRENT_LIST_DIR}/minispi.c
    ${CMAKE_CURRENT_LIST_DIR}/sprites.c
    ${CMAKE_CURRENT_LIST_DIR}/intensidades.c

    ${CMAKE_CURRENT_LIST_DIR}/ventilagon/audio.c
    ${CMAKE_CURRENT_LIST_DIR}/ventilagon/board.c
    ${CMAKE_CURRENT_LIST_DIR}/ventilagon/display.c
    ${CMAKE_CURRENT_LIST_DIR}/ventilagon/ledbar.c
    ${CMAKE_CURRENT_LIST_DIR}/ventilagon/levels.c
    ${CMAKE_CURRENT_LIST_DIR}/ventilagon/patterns.c
    ${CMAKE_CURRENT_LIST_DIR}/ventilagon/ship.c
    ${CMAKE_CURRENT_LIST_DIR}/ventilagon/state_base.c
    ${CMAKE_CURRENT_LIST_DIR}/ventilagon/state_gameover.c
    ${CMAKE_CURRENT_LIST_DIR}/ventilagon/state_play.c
    ${CMAKE_CURRENT_LIST_DIR}/ventilagon/state_resetting.c
    ${CMAKE_CURRENT_LIST_DIR}/ventilagon/state_win.c
    ${CMAKE_CURRENT_LIST_DIR}/ventilagon/state_win_credits.c
    ${CMAKE_CURRENT_LIST_DIR}/ventilagon/text_bitmap.c
    ${CMAKE_CURRENT_LIST_DIR}/ventilagon/transformations.c
    ${CMAKE_CURRENT_LIST_DIR}/ventilagon/ventilagon.h
    ${CMAKE_CURRENT_LIST_DIR}/ventilagon/ventilagon_rotor.c
)

# Add the current directory as an include directory.
target_include_directories(usermod_povdisplay INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}
)

# Link our INTERFACE library to the usermod target.
target_link_libraries(usermod INTERFACE usermod_povdisplay)
