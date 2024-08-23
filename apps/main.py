from director import director
import imagenes
import menu

def update_over_the_air():
    import ota_update
    director.push(ota_update.Update())

class GamesMenu(menu.Menu):
    OPTIONS = [
        ('vyruss', 7, 0, 64),
        ('bembi', 43, 0, 64),
        ('vladfarty', 7, 2, 64),
        #('credits', 7, 3, 64),
        #('ventap', 7, 4, 64),
        ('ventilagon', 7, 1, 64),
    ]

    def on_enter(self):
        super(GamesMenu, self).on_enter()
        self.animation_frames = 0
        self.pollitos = self.sprites[1]

    def on_option_pressed(self, option_index):
        option_pressed = self.options[option_index]
        print(option_pressed)
        if option_pressed[0] == 'vyruss':
            import vyruss
            director.push(vyruss.VyrusGame())
            raise StopIteration()
        if option_pressed[0] == 'credits':
            import credits
            director.push(credits.Credits())
            raise StopIteration()
        if option_pressed[0] == 'bembi':
            import bembi
            director.push(bembi.Bembidiona())
            raise StopIteration()
        if option_pressed[0] == 'ventap':
            import ventap
            director.push(ventap.Ventap())
            raise StopIteration()
        if option_pressed[0] == 'vladfarty':
            import vladfarty
            director.push(vladfarty.VladFarty())
            raise StopIteration()
        if option_pressed[0] == 'ventilagon':
            import ventilagon_game
            director.push(ventilagon_game.VentilagonGame())
            raise StopIteration()

    def check_debugmode(self):
        if (director.is_pressed(director.JOY_UP)
            and director.is_pressed(director.JOY_LEFT)
            and director.is_pressed(director.JOY_RIGHT)
            and director.is_pressed(director.BUTTON_A) ):
            import debugmode
            director.push(debugmode.DebugMode())
            return True
            
    def step(self):
        if not self.check_debugmode():
            super(GamesMenu, self).step()

            if director.is_pressed(director.BUTTON_D) \
                and director.is_pressed(director.BUTTON_B)\
                and director.is_pressed(director.BUTTON_C):
                pass
                #update_over_the_air()

            self.animation_frames += 1
            pf = (self.animation_frames // 4) % 5
            self.pollitos.set_frame(pf)

def main():
    # init images
    director.register_strip(0, imagenes.galaga_png)
    director.register_strip(1, imagenes.numerals_png)
    director.register_strip(2, imagenes.gameover_png)
    director.register_strip(3, imagenes.disparo_png)
    director.register_strip(4, imagenes.ll9_png)
    director.register_strip(5, imagenes.explosion_png)
    director.register_strip(6, imagenes.explosion_nave_png)
    director.register_strip(7, imagenes.menu_png)
    director.register_strip(8, imagenes.credits_png)
    director.register_strip(10, imagenes.tierra_png)
    director.register_strip(11, imagenes.marte_png)
    director.register_strip(12, imagenes.jupiter_png)
    director.register_strip(13, imagenes.saturno_png)
    director.register_strip(14, imagenes.sves_png)
    director.register_strip(15, imagenes.ventilastation_png)
    director.register_strip(16, imagenes.tecno_estructuras_png)
    director.register_strip(17, imagenes.menatwork_png)
    director.register_strip(18, imagenes.vladfartylogo_png)
    director.register_strip(19, imagenes.vga_pc734_png)
    director.register_strip(20, imagenes.vga_cp437_png)
    director.register_strip(21, imagenes.vladfartylogo_png)
    director.register_strip(22, imagenes.farty_lion_png)
    director.register_strip(23, imagenes.ready_png)
    director.register_strip(24, imagenes.bg64_png)
    director.register_strip(25, imagenes.copyright_png)
    director.register_strip(26, imagenes.bgspeccy_png)
    director.register_strip(27, imagenes.reset_png)
    director.register_strip(28, imagenes.farty_lionhead_png)
    director.register_strip(29, imagenes.rainbow437_png)
    director.register_strip(30, imagenes.chanime01_png)
    director.register_strip(31, imagenes.chanime02_png)
    director.register_strip(32, imagenes.chanime03_png)
    director.register_strip(33, imagenes.chanime04_png)
    director.register_strip(34, imagenes.chanime05_png)
    director.register_strip(35, imagenes.chanime06_png)
    director.register_strip(36, imagenes.chanime07_png)
    director.register_strip(37, imagenes.salto01_png)
    director.register_strip(38, imagenes.salto02_png)
    director.register_strip(39, imagenes.salto03_png)
    director.register_strip(40, imagenes.salto04_png)
    director.register_strip(41, imagenes.salto05_png)
    director.register_strip(42, imagenes.salto06_png)
    director.register_strip(43, imagenes.pollitos_png)
    director.register_strip(44, imagenes.bembi_png)

    director.push(GamesMenu())
    director.run()

if __name__ == '__main__':
    import machine
    try:
        main()
    except Exception as e:
        print(e)
        machine.reboot()
