import pyglet

class PitchTest(pyglet.window.Window):
    def __init__(self):
        super(PitchTest, self).__init__()
        self.sound = pyglet.media.StaticSource(pyglet.media.synthesis.Sine(0.5, frequency=440))

    def on_key_press(self, symbol, modifiers):
        if symbol == pyglet.window.key.A:
            self.sound.play()
        elif symbol == pyglet.window.key.S:
            player = self.sound.play()
            player.pitch = 2.0
        elif symbol == pyglet.window.key.D:
            player = pyglet.media.Player()
            player.pitch = 2.0
            player.queue(self.sound)
            player.play()

if __name__ == '__main__':
    print(pyglet.media.get_audio_driver())
    window = PitchTest()
    pyglet.app.run()
