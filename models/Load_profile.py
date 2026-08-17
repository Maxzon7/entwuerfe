import datetime

class load_profile:

    def __init__(self, name: str = "", power: float = 0.0):
        self.name = name
        self.power = power
        self.operation_hours = []  # Liste aus (Startzeit, Endzeit)-Paaren

    def add_operation_window(self, start_time: datetime.time, end_time: datetime.time):
        """Fügt einen genau definierten Zeitraum hinzu."""
        self.operation_hours.append((start_time, end_time))

    def clear_operation_windows(self):
        """Löscht alle gespeicherten Zeiträume."""
        self.operation_hours = []
