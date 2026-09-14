# baddie_formation.py  -- generated, do not edit. body-sha: 38477948
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

    state = ('remaining', 'x_dir', 'formation_done', 'attack_distance', 'in_attack_run')

    states = ('closer1', 'xmove1', 'closer2', 'xmove2', 'away', 'formed', 'attack_closer', 'attack_away')
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
        sprite.in_attack_run = False

    def formed(self, sprite):
        pass

    def enter_attack_closer(self, sprite):
        sprite.remaining = sprite.attack_distance
        sprite.in_attack_run = True

    def attack_closer(self, sprite):
        sprite.y += (0 - min(self.y_speed, sprite.remaining))
        sprite.remaining += (0 - min(self.y_speed, sprite.remaining))
        if sprite.remaining <= 0:
            return 'attack_away'

    def enter_attack_away(self, sprite):
        sprite.remaining = sprite.attack_distance

    def attack_away(self, sprite):
        sprite.y += min(self.y_speed, sprite.remaining)
        sprite.remaining += (0 - min(self.y_speed, sprite.remaining))
        if sprite.remaining <= 0:
            return 'formed'

# behavior-blocks: eNrtWd9vmzAQ/lciS5O6jWmFNlWHtpdp2vMeN00VcsBpvBobYdOCKv73nYnN76Zkaap2Qnkh5nzfffZ9d7Fzj3CoqOAS+b+vHISThBWBEgFmbDsSMixlwHFMkI++4iii5LtIY6wnIQclOMWxnnyPIrLGGVPIP3MQwysCDtDPhUwIicAwxjny3Qt4oBz5pw4yLvPAWkhFEjBxkCoS/YZn8Yqk8CLjFLyiULCPioY3qHRaYF4D9utRsGIyGCPRCNjlskH7scGSLNzFSciEJOlbC+stlwbXrXG3Jm4QUakwD8m0ALrYruv1wb3FiaQRucOF3Amf74UM69xFPjvvA5/twdo7iPWniz72+VTS3kGkzwdbvVycYEDdCaoNDuLrLVuEv1GZMFws7mikNhZ2qfOgB2sNJrEEUSckBSWkVJGtyCHe6hGlJMaUU34Nc3IgoueurdyDSHBNCiuFw5s2TcoDM5hmHFmHQYzDDYUp/j1aCSgcUj8ZQ71S+ivhCiLU9eOG8ghilEQF23jquDph3WKWVS6tvbG1O9ALriyv7LoABo5FxlVr9opynBaBSMADI+v2q6q0oUHtKB0E1n61BQ5K6fVGPRxNE3gJ84wNDsMszliXYlHlwT7xMdi+FLNmSU5taB9GAntGoo8wbZkC41DwiFbNpPEdihhiIsNIHwY1sX7+MhLqyEKBPWHSZL8xo+ugGgP1bAhvp+S1gI7Yw9aq0It0BZ9aEtuK9zxp7ex03VXk0P1gTVSakX/XymvNxVl1r0t17eZhpfdUjaS3Id1WPreROaGP30bMOeEY6Tw4gszFftbGy9ZGHotb4na14R1PG96sjVkbr0obntWG6SJTpTE40U88HTzxkWONgW9bapqKEf0RVJ4/2Px2+M9H/O7I5R2v+htYJ837/eTS91Pd0lhf7w6SXn6w9OzMNyPzemDbO6uyfCl1J5/rzoS6Y7uwKTymDB1Drd5/odYnS+Rx2c+6n3X/PBcv9Y1Lqa/7gQJmzanS0tV/BLbGTC9vfrvXBcNc29S/XPo3qE7npkdXGpmt/pBQBXYThagYklRWi+mWfwFZzGhQ
