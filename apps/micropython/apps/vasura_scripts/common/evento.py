class Evento:
    
    def __init__(self):
        self.suscriptores : List[callable] = []

    def disparar(self, value = None):
        if value:
            [callback(value) for callback in self.suscriptores]
        else:
            [callback() for callback in self.suscriptores]

    def suscribir(self, callback:callable):
        if not callback:
            return
        
        self.suscriptores.append(callback)
    
    def desuscribir(self, callback:callable):
        if not callback in self.suscriptores:
            return
        
        self.suscriptores.remove(callback)