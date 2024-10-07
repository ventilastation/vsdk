VENTILASTATION_MODULES=`pwd`/modules/micropython.cmake
#VENTILASTATION_MODULES=`pwd`/micropython/examples/usercmodule/micropython.cmake

cd micropython/ports/esp32

PARAMS="-j V=1 BOARD=ESP32_GENERIC_S3 BOARD_VARIANT=SPIRAM_OCT PORT=/dev/ttyACM0 USER_C_MODULES=$VENTILASTATION_MODULES"
#make $PARAMS clean
make $PARAMS $1
#make $PARAMS deploy
