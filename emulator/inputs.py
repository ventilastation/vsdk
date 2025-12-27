try:
    # Botones de la base de Super Ventilagon
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setup([9,10], GPIO.IN, GPIO.PUD_UP)

    def base_button_left():
        return GPIO.input(9) == 0
    
    def base_button_right():
        return GPIO.input(10) == 0

except ImportError:
    def base_button_left():
        return False

    def base_button_right():
        return False
