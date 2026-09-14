# baddie_formation.py  -- generated, do not edit. body-sha: a98942cf
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

    state = ('remaining', 'x_dir', 'finished')

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
        sprite.finished = True

    def formed(self, sprite):
        pass

# behavior-blocks: eNrtWMGO2jAQ/RVkqRJtU3UTltUWtZeq6rnHVhWKTDKAu44dxc5uIsS/dxxsEkJgoZRVqRAHImdm3jx73oxhQWikmRSKjH6OPULTlJehliHlfLUScapUKGgCZEQ+0zhm8FVmCTVOxCMpzWhinBckhinNuSajgUc4nQAGIN97KgWI0TChBRn5d/jABBndeMSGLEJnoTSkaOIRXabmjciTCWT4IhcMo5JI8veaRQ9k6TXAghrsx7Ng5cFgHOIOsPthjfZtThX0/F4/4lJB9trBBsOhxfXXuCsTP4yZ0lREcFgCm9i+H7TBg15fsRieaKn2whdHIeM+byIPbtvAgyNYByex/nDXxr49lHRwEunbraMe9voUUfeCGoOT+AbDBuEvTKWclr0nFuu5gx2aOmjBOoODWKKoU8hQCRnTsBI55ls9kgwSygQTM/QpkIjxneKCmmOizjBMaDRnAh0WZCKxISjzZKibbxAaIU1DeGAiRlAFOlwBrIE2cB4pz6tY1r5qKWTHli6XY0cTEWgic6EbvhMmaFaGMkV/DlO9O6xrBUuPoPWo2lGPZGw2bzq5vK1TnfYS/awNjaI8yfkmwbI61mPy43gaGeX1hty41N51JPaCRJ9h2jBFxpEUMatmQx07kgnmBNuZ7ga1uX781JFqx0ahPXBli9masWlYraEY5iCaBTmTOOBa2FOcaWaTxvjxXL8+RzlvjYI/r+hLrZirNi5LG0UiH8Hf1EZwPm0EV21ctXFR2gicNuwUOVQa65vVtjK2ktVZDk05GDgrzDMosdg5oPbELzri7qm3Pa/am7w+2LfHlXQ7TnWjdbHenCSP4mR5OM9XHX4tsNX93rj8G72huPaGA3qDm5S2OdhWcQ61Bv+FWv9aIXfL/qr7q+5fRPfVPyGV6DEWJqEZ5fUvP0fX/GnaWLOzvL5frxuGtwq4vl2YXqLyyS+IdOiOScqKA2Sq2i5/+RulpxfB
