# baddie_formation.py  -- generated, do not edit. body-sha: a82bf038
from vs2.behaviors import StateMachine
from vs2.params import Number


class BaddieFormation(StateMachine):
    x_speed = Number(3, min=0, max=16, step=1, label='X speed', unit='col/tick')
    y_speed = Number(2, min=0, max=16, step=1, label='Y speed', unit='led/tick')
    closer1_distance = Number(85, min=1, max=255, step=1, label='Phase 1 (closer)', unit='led')
    x1_distance = Number(112, min=1, max=255, step=1, label='Phase 2 (sideways)', unit='col')
    closer2_distance = Number(34, min=1, max=255, step=1, label='Phase 3 (closer)', unit='led')
    x2_distance = Number(96, min=1, max=255, step=1, label='Phase 4 (sideways)', unit='col')
    away_distance = Number(45, min=1, max=255, step=1, label='Phase 5 (away)', unit='led')
    width = Number(256, min=1, max=512, step=1, label='Display width', unit='col')

    state = ('remaining', 'x_dir', 'formation_done')

    states = ('closer1', 'xmove1', 'closer2', 'xmove2', 'away', 'formed')
    initial = 'closer1'

    def enter_closer1(self, sprite):
        sprite.remaining = self.closer1_distance

    def closer1(self, sprite):
        sprite.y += (0 - min(self.y_speed, sprite.remaining))
        sprite.remaining += (0 - min(self.y_speed, sprite.remaining))
        if sprite.remaining <= 0:
            return 'xmove1'

    def enter_xmove1(self, sprite):
        sprite.remaining = self.x1_distance

    def xmove1(self, sprite):
        sprite.x = ((sprite.x + (sprite.x_dir * min(self.x_speed, sprite.remaining))) % self.width)
        sprite.remaining += (0 - min(self.x_speed, sprite.remaining))
        if sprite.remaining <= 0:
            return 'closer2'

    def enter_closer2(self, sprite):
        sprite.remaining = self.closer2_distance

    def closer2(self, sprite):
        sprite.y += (0 - min(self.y_speed, sprite.remaining))
        sprite.remaining += (0 - min(self.y_speed, sprite.remaining))
        if sprite.remaining <= 0:
            return 'xmove2'

    def enter_xmove2(self, sprite):
        sprite.remaining = self.x2_distance

    def xmove2(self, sprite):
        sprite.x = ((sprite.x + ((0 - sprite.x_dir) * min(self.x_speed, sprite.remaining))) % self.width)
        sprite.remaining += (0 - min(self.x_speed, sprite.remaining))
        if sprite.remaining <= 0:
            return 'away'

    def enter_away(self, sprite):
        sprite.remaining = self.away_distance

    def away(self, sprite):
        sprite.y += min(self.y_speed, sprite.remaining)
        sprite.remaining += (0 - min(self.y_speed, sprite.remaining))
        if sprite.remaining <= 0:
            return 'formed'

    def enter_formed(self, sprite):
        sprite.formation_done = True

    def formed(self, sprite):
        pass

# behavior-blocks: eNrtWFFv2jAQ/ivI0qRuy7QmlKqLtpdp2vMeN00oMslRvDp2FDttIsR/3znYJIRAYYxqTIgHIufuvvvO950Nc0JjzaRQJPw59gjNMl5FWkaU8+VKzKlSkaApkJB8pknC4KvMU2qciEcymtPUOM9JAlNacE3CoUc4nQAGIN8HKgNI0DClJQn9W3xggoTXHrEhy8hZKA0ZmnhEV5l5I4p0Ajm+KATDqCSW/L1m8QNZeC2woAH78SxYtTcYh6QH7G7UoH2bUQUDf3AVc6kgf+1gg9HI4vor3KWJHyVMaSpi2C+BdWzfD7rgweBKsQSeaKV2wpcHIWOd15GHN13g4QGsg6NYf7jtYt/sSzo4ivTNxlaPBlcUUXeCGoOj+AajFuEvTGWcVoMnluiZgx2ZPujAOoO9WKKoM8hRCTnTsBQ55ls/khxSygQT9+hTIhHjO3VyjxIpgDjzKKXxjOFCOCcTiWNBmSdTAPMNQiOwGQsPTCQIrUBHS5gV3BraI+VFHcva14OFbCnsYjF2ZBGBprIQuuU7YYLmVSQz9Ocw1dvDuoGw8Ahah3VdPZKz+1nbyeVtnZq0F+hnbWgcF2nB1wlW9eYekh/HPckpbwpy7VJ715PYCxJ9hmnLFBnHUiSsPiGa2LFMMSfYzHQ7qM3146eeVHsKhfbAlW1pa8amUb2GkpiBaDfkvcRjroNtWt0UaYwfz03tU7TzxoHw5x19rh1z0cZ5aaNM5SP469oITqeN4KKNizbOShuB04Y9RfaVRud+tamPjZR1XkBbFAbUyvMEeiy3HlM74pc9cXd03Y5X3VKvtvftYY3djVPfbl2sN0eJpDxaJM7zVY9fB2x51zcu/8aEKC8TYo8J4c5LOyLswDiFWoP/Qq1/rZH7ZX/R/UX3L6L7+v+QWvQYC5PQjPLm95+ja/5Aba3Zs7y5Za8GhrcMuLpjmFmiiskviHXktknKmgPkqi6Xv/gN8vcc1Q==
